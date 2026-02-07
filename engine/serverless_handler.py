import runpod
import os
import json
import base64
import time
import requests
from io import BytesIO
import glob
import subprocess
import sys

# URL локального ComfyUI (внутри контейнера Serverless)
COMFY_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "/app/ComfyUI/output"
MODELS_DIR = "/app/ComfyUI/models/checkpoints"
CHECKPOINT_FILE = f"{MODELS_DIR}/juggernautXL_v9.safetensors"

# Deepfake models path
INSIGHTFACE_DIR = "/app/ComfyUI/models/insightface"

def log(message):
    print(f"[Handler] {message}", flush=True)

def check_comfy_status():
    """Ожидание готовности ComfyUI"""
    log("Checking ComfyUI status...")
    for i in range(60): # 60 seconds wait
        try:
            response = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if response.status_code == 200:
                log("ComfyUI is ready.")
                return True
        except Exception:
            pass
        time.sleep(1)
    log("ComfyUI not ready after 60s.")
    return False

def ensure_models():
    """Минимальная проверка и быстрая загрузка модели, если отсутствует"""
    try:
        if not os.path.exists(MODELS_DIR):
            os.makedirs(MODELS_DIR, exist_ok=True)
        
        if not os.path.exists(CHECKPOINT_FILE):
            log(f"Model not found at {CHECKPOINT_FILE}. Downloading...")
            # Загрузка с CivitAI (прямая ссылка на Juggernaut XL v9)
            url = "https://civitai.com/api/download/models/348913?type=Model&format=SafeTensor&size=pruned&fp=fp16"
            # Используем stream=True и большой таймаут
            r = requests.get(url, stream=True, timeout=600)
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(CHECKPOINT_FILE, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (100 * 1024 * 1024) == 0:
                            log(f"Downloaded {downloaded / 1024 / 1024:.0f} MB / {total_size / 1024 / 1024:.0f} MB")
            log("Model download complete.")
        else:
            log("Model exists.")
            
        # Ensure InsightFace models exist (if directory is empty, download them)
        # This part will be enabled once we add insightface lib
        # if not os.path.exists(INSIGHTFACE_DIR):
        #     os.makedirs(INSIGHTFACE_DIR, exist_ok=True)
            
    except Exception as e:
        log(f"Model download failed: {e}")
        pass

def latest_image_b64():
    """Находит последнюю картинку в output и возвращает base64"""
    try:
        files = sorted(
            glob.glob(os.path.join(OUTPUT_DIR, "**", "*.png"), recursive=True),
            key=os.path.getmtime,
            reverse=True
        )
        if not files:
            return None
        # Проверяем, что файл создан недавно (в рамках этой задачи)
        if time.time() - os.path.getmtime(files[0]) > 600:
            return None
            
        with open(files[0], "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        log(f"Error reading image: {e}")
        return None

def build_workflow(prompt_text, negative_prompt, width, height, seed, steps, cfg, sampler_name, scheduler, high_res_fix=True, face_swap_image=None):
    """
    Строит JSON Workflow для ComfyUI.
    high_res_fix=True включает 2-pass генерацию (Latent Upscale).
    face_swap_image: base64 string of face image (if provided)
    """
    # Базовые ноды
    workflow = {
        "10": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": os.path.basename(CHECKPOINT_FILE)}
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text or "beautiful woman",
                "clip": ["10", 1]
            }
        },
        "12": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["10", 1]
            }
        },
        "13": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1}
        },
        "14": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "model": ["10", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["13", 0],
                "denoise": 1.0
            }
        },
        "15": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["14", 0], "vae": ["10", 2]}
        },
        "16": {
            "class_type": "SaveImage",
            "inputs": {"images": ["15", 0], "filename_prefix": "runpod_base_"}
        }
    }

    # High-Res Fix
    last_image_node = "15" # VAE Decode output
    
    if high_res_fix:
        workflow["20"] = {
            "class_type": "LatentUpscaleBy",
            "inputs": {
                "samples": ["14", 0],
                "upscale_method": "nearest-exact",
                "scale_by": 1.5
            }
        }
        workflow["21"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": int(steps / 2) + 5,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": "karras",
                "model": ["10", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["20", 0],
                "denoise": 0.55
            }
        }
        workflow["22"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["21", 0], "vae": ["10", 2]}
        }
        last_image_node = "22"
        
        # Обновляем SaveImage
        workflow["23"] = {
            "class_type": "SaveImage",
            "inputs": {"images": [last_image_node, 0], "filename_prefix": "runpod_hires_"}
        }

    # Face Swap (Placeholder logic for future)
    if face_swap_image:
        # Здесь будет логика добавления нод ReActor
        # 30: LoadImage (Face)
        # 31: ReActorFaceSwap
        # workflow["31"] = { ... inputs: {"input_image": [last_image_node, 0], "source_image": ["30", 0]} ... }
        # last_image_node = "31"
        pass

    return workflow

def handler(job):
    """
    Основная функция-обработчик RunPod Serverless.
    """
    try:
        log(f"Received job: {job}")
        job_input = job["input"]
        prompt_text = job_input.get("prompt", "")
        width = int(job_input.get("width", 1024))
        height = int(job_input.get("height", 1024))
        steps = int(job_input.get("steps", 25))
        cfg = float(job_input.get("cfg", 7.0))
        sampler_name = job_input.get("sampler_name", "dpmpp_2m")
        scheduler = job_input.get("scheduler", "karras")
        seed = int(job_input.get("seed", 0))
        negative_prompt = job_input.get("negative_prompt", "text, watermark, blur, deformed, painting, cartoon, low quality, ugly")
        
        enable_highres = job_input.get("highres_fix", True)
        face_swap_img = job_input.get("face_image", None) # Base64 string if present

        # 1. Запуск ComfyUI (если нужно)
        if not check_comfy_status():
            log("Forcing numpy<2.0.0 to prevent torch conflict...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "numpy<2.0.0"], check=True)
                log("Numpy downgrade complete.")
            except Exception as e:
                log(f"Failed to downgrade numpy: {e}")

            log("Starting ComfyUI...")
            subprocess.Popen(["python3", "/app/ComfyUI/main.py", "--listen", "0.0.0.0", "--port", "8188"])
            if not check_comfy_status():
                 return {"error": "ComfyUI failed to start"}

        # 2. Проверка моделей
        ensure_models()

        # 3. Формируем API prompt (Workflow)
        prompt = build_workflow(
            prompt_text, negative_prompt, width, height, seed, steps, cfg, sampler_name, scheduler, 
            high_res_fix=enable_highres,
            face_swap_image=face_swap_img
        )
        
        log(f"Generated prompt: {json.dumps(prompt)}")

        # 4. Отправка задачи в ComfyUI API
        try:
            try:
                os.makedirs("/app/ComfyUI/user", exist_ok=True)
                with open("/app/ComfyUI/user/last_prompt.json", "w") as f:
                    json.dump(prompt, f)
            except Exception:
                pass

            p = {"prompt": prompt, "client_id": "serverless"}
            response = requests.post(f"{COMFY_URL}/prompt", json=p)
            
            log(f"ComfyUI response: {response.status_code} - {response.text}")
            
            if response.status_code != 200:
                return {"error": f"ComfyUI /prompt failed: {response.text}", "debug_prompt": prompt}
                
            prompt_id = response.json().get("prompt_id")
            log(f"Prompt ID: {prompt_id}")
            
        except Exception as e:
            log(f"Failed to queue prompt: {e}")
            return {"error": f"Failed to queue prompt: {str(e)}", "debug_prompt": prompt}

        # 5. Ожидание результата
        log("Waiting for image generation...")
        deadline = time.time() + 600
        img_b64 = None
        
        while time.time() < deadline:
            img_b64 = latest_image_b64()
            if img_b64:
                log("Image found!")
                break
            time.sleep(2)
            
        if not img_b64:
            log("Timeout waiting for image.")
            return {"error": "Timeout waiting for output image", "debug_prompt": prompt}

        return {"status": "success", "image_base64": img_b64}
        
    except Exception as fatal_error:
        import traceback
        err_msg = f"FATAL HANDLER ERROR: {str(fatal_error)}\n{traceback.format_exc()}"
        log(err_msg)
        return {"error": err_msg}

runpod.serverless.start({"handler": handler})
