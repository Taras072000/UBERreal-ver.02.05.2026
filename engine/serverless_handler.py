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
CHECKPOINT_FILE = f"{MODELS_DIR}/RealVisXL_V4.0.safetensors"
VAE_DIR = "/app/ComfyUI/models/vae"
VAE_FILE = f"{VAE_DIR}/sdxl_vae.safetensors"
LORA_DIR = "/app/ComfyUI/models/loras"
LORA_FILE = f"{LORA_DIR}/Hinata_SDXL.safetensors"

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

        # Rename old model if exists (migration from previous version)
        old_checkpoint = f"{MODELS_DIR}/juggernautXL_v9.safetensors"
        if os.path.exists(old_checkpoint) and not os.path.exists(CHECKPOINT_FILE):
            log(f"Renaming {old_checkpoint} to {CHECKPOINT_FILE}")
            os.rename(old_checkpoint, CHECKPOINT_FILE)
        
        if not os.path.exists(CHECKPOINT_FILE):
            log(f"Model not found at {CHECKPOINT_FILE}. Downloading...")
            
            # RealVisXL V4.0 (Lightning / Turbo или обычный - берем обычный для качества)
            urls = [
                "https://civitai.com/api/download/models/361593?type=Model&format=SafeTensor&size=pruned&fp=fp16", # RealVisXL V4.0
                "https://huggingface.co/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors" # HF Mirror
            ]
            
            # Hugging Face Token from Environment Variable
            hf_token = os.environ.get("HF_TOKEN")
            headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
            
            success = False
            for url in urls:
                try:
                    log(f"Trying to download from: {url}")
                    # Use headers only for HF URLs
                    req_headers = headers if "huggingface.co" in url else {}
                    
                    r = requests.get(url, stream=True, timeout=600, headers=req_headers)
                    if r.status_code == 200:
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
                        success = True
                        break
                    else:
                        log(f"Failed with status {r.status_code}")
                except Exception as e:
                    log(f"Download failed: {e}")
            
            if not success:
                log("ALL DOWNLOAD MIRRORS FAILED. Check internet or URLs.")
        else:
            log("Model exists.")

        # Download VAE
        if not os.path.exists(VAE_DIR):
            os.makedirs(VAE_DIR, exist_ok=True)
        if not os.path.exists(VAE_FILE):
            log(f"Downloading VAE to {VAE_FILE}...")
            # Using HuggingFace mirror for stability
            vae_url = "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl.vae.safetensors"
            try:
                r = requests.get(vae_url, stream=True, timeout=600)
                if r.status_code == 200:
                    with open(VAE_FILE, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("VAE downloaded.")
                else:
                    log(f"VAE download failed with status {r.status_code}")
            except Exception as e:
                log(f"VAE download failed: {e}")


        # Download LoRA (Hinata)
        if not os.path.exists(LORA_DIR):
            os.makedirs(LORA_DIR, exist_ok=True)
        if not os.path.exists(LORA_FILE):
            log(f"Downloading LoRA to {LORA_FILE}...")
            lora_url = "https://civitai.com/api/download/models/287086?type=Model&format=SafeTensor" # Hinata SDXL
            try:
                r = requests.get(lora_url, stream=True, timeout=600)
                if r.status_code == 200:
                    with open(LORA_FILE, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("LoRA downloaded.")
            except Exception as e:
                log(f"LoRA download failed: {e}")
            
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
    # Detailer prompts
    detail_prompt = ", (detailed skin texture:1.3), (detailed nipples:1.2), (detailed pussy:1.2), (hyperdetailed:1.2)"
    
    workflow = {
        "10": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": os.path.basename(CHECKPOINT_FILE)}
        },
        "19": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": os.path.basename(VAE_FILE)}
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": (prompt_text or "beautiful woman") + detail_prompt,
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
            "inputs": {"samples": ["14", 0], "vae": ["19", 0]}
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
                "sampler_name": "dpmpp_sde",
                "scheduler": "karras",
                "model": ["100", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["20", 0],
                "denoise": 0.65
            }
        }
        workflow["22"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["21", 0], "vae": ["19", 0]}
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

import shutil

# ... (imports)

# ... (constants)

def clear_output_dir():
    """Очистка папки output перед генерацией, чтобы не отправить старую картинку"""
    if os.path.exists(OUTPUT_DIR):
        try:
            shutil.rmtree(OUTPUT_DIR)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            log("Output directory cleared.")
        except Exception as e:
            log(f"Failed to clear output dir: {e}")

def handler(job):
    """
    Основная функция-обработчик RunPod Serverless.
    """
    try:
        log(f"Received job: {job}")
        
        # Очищаем старые картинки перед запуском
        clear_output_dir()
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
