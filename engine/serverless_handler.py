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
CHECKPOINT_FILE = f"{MODELS_DIR}/PonyRealism_v2.1.safetensors"
VAE_DIR = "/app/ComfyUI/models/vae"
VAE_FILE = f"{VAE_DIR}/sdxl_vae.safetensors"
LORA_DIR = "/app/ComfyUI/models/loras"
LORA_HINATA = f"{LORA_DIR}/Hinata_SDXL.safetensors"
LORA_CUM = f"{LORA_DIR}/Cum_Shot_SDXL.safetensors"
LORA_DETAIL = f"{LORA_DIR}/Detail_Slider_SDXL.safetensors"
LORA_EXPRESSIONS = f"{LORA_DIR}/Expressions_SDXL.safetensors"

CONTROLNET_DIR = "/app/ComfyUI/models/controlnet"
CONTROLNET_FILE = f"{CONTROLNET_DIR}/controlnet-openpose-sdxl-1.0.safetensors"

# Impact Pack Models
BBOX_DIR = "/app/ComfyUI/models/ultralytics/bbox"
SAM_DIR = "/app/ComfyUI/models/sams"
BBOX_MODEL = f"{BBOX_DIR}/face_yolov8n.pt"
SAM_MODEL = f"{SAM_DIR}/sam_vit_b_01ec64.pth"

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
            
            # Pony Realism v2.1 Main
            urls = [
                "https://civitai.com/api/download/models/534642?type=Model&format=SafeTensor", 
                "https://huggingface.co/LyliaEngine/ponyRealism_v21MainVAE/resolve/main/ponyRealism_v21MainVAE.safetensors"
            ]
            
            # Hugging Face Token from Environment Variable
            hf_token = os.environ.get("HF_TOKEN")
            headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
            # CivitAI often requires User-Agent to avoid 403
            civitai_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            
            success = False
            for url in urls:
                try:
                    log(f"Trying to download from: {url}")
                    # Use headers only for HF URLs, use civitai_headers for CivitAI
                    req_headers = headers if "huggingface.co" in url else civitai_headers
                    
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
        civitai_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        if not os.path.exists(LORA_DIR):
            os.makedirs(LORA_DIR, exist_ok=True)
            
        if not os.path.exists(LORA_HINATA):
            log(f"Downloading Hinata LoRA...")
            try:
                # CivitAI: Hinata (SDXL)
                r = requests.get("https://civitai.com/api/download/models/287086?type=Model&format=SafeTensor", stream=True, timeout=600, headers=civitai_headers)
                if r.status_code == 200:
                    with open(LORA_HINATA, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("Hinata LoRA downloaded.")
                else:
                    log(f"Hinata LoRA download failed: {r.status_code}")
            except Exception as e:
                log(f"Hinata LoRA download failed: {e}")

        # Download LoRA (Cum Shot)
        if not os.path.exists(LORA_CUM):
            log(f"Downloading Cum LoRA...")
            try:
                # CivitAI: Cum Shot (SDXL)
                r = requests.get("https://civitai.com/api/download/models/139556?type=Model&format=SafeTensor", stream=True, timeout=600, headers=civitai_headers)
                if r.status_code == 200:
                    with open(LORA_CUM, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("Cum LoRA downloaded.")
                else:
                    log(f"Cum LoRA download failed: {r.status_code}")
            except Exception as e:
                log(f"Cum LoRA download failed: {e}")
                
        # Download LoRA (Detail Slider)
        if not os.path.exists(LORA_DETAIL):
            log(f"Downloading Detail LoRA...")
            try:
                # CivitAI: Skin Detail / Detail Slider
                r = requests.get("https://civitai.com/api/download/models/135931?type=Model&format=SafeTensor", stream=True, timeout=600, headers=civitai_headers)
                if r.status_code == 200:
                    with open(LORA_DETAIL, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("Detail LoRA downloaded.")
                else:
                    log(f"Detail LoRA download failed: {r.status_code}")
            except Exception as e:
                log(f"Detail LoRA download failed: {e}")

        # Download LoRA (Expressions)
        if not os.path.exists(LORA_EXPRESSIONS):
            log(f"Downloading Expressions LoRA...")
            try:
                # CivitAI: Expressions
                r = requests.get("https://civitai.com/api/download/models/121545?type=Model&format=SafeTensor", stream=True, timeout=600, headers=civitai_headers)
                if r.status_code == 200:
                    with open(LORA_EXPRESSIONS, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("Expressions LoRA downloaded.")
                else:
                    log(f"Expressions LoRA download failed: {r.status_code}")
            except Exception as e:
                log(f"Expressions LoRA download failed: {e}")

        # Impact Pack Models
        if not os.path.exists(BBOX_DIR): os.makedirs(BBOX_DIR, exist_ok=True)
        if not os.path.exists(SAM_DIR): os.makedirs(SAM_DIR, exist_ok=True)
        
        if not os.path.exists(BBOX_MODEL):
            log("Downloading Face YOLO model...")
            try:
                r = requests.get("https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8n.pt", stream=True, timeout=600)
                with open(BBOX_MODEL, "wb") as f: f.write(r.content)
            except Exception as e: log(f"YOLO download failed: {e}")

        if not os.path.exists(SAM_MODEL):
            log("Downloading SAM model...")
            try:
                r = requests.get("https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth", stream=True, timeout=600)
                with open(SAM_MODEL, "wb") as f: 
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk: f.write(chunk)
            except Exception as e: log(f"SAM download failed: {e}")

        # Download ControlNet (OpenPose)
        if not os.path.exists(CONTROLNET_DIR):
            os.makedirs(CONTROLNET_DIR, exist_ok=True)
        if not os.path.exists(CONTROLNET_FILE):
            log(f"Downloading ControlNet to {CONTROLNET_FILE}...")
            cn_url = "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors"
            try:
                r = requests.get(cn_url, stream=True, timeout=600)
                if r.status_code == 200:
                    with open(CONTROLNET_FILE, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("ControlNet downloaded.")
                else:
                    log(f"ControlNet download failed: {r.status_code}")
            except Exception as e:
                log(f"ControlNet download failed: {e}")
            
        # Ensure InsightFace models exist (if directory is empty, download them)
        if not os.path.exists(INSIGHTFACE_DIR):
            os.makedirs(INSIGHTFACE_DIR, exist_ok=True)
            
        # Check specific models folder usually expected by ReActor/InsightFace
        # ReActor expects models in: models/insightface/models/antelopev2 or buffalo_l
        # Let's create the structure
        IF_MODELS_PATH = os.path.join(INSIGHTFACE_DIR, "models", "buffalo_l")
        if not os.path.exists(IF_MODELS_PATH):
            os.makedirs(IF_MODELS_PATH, exist_ok=True)
            log(f"Downloading InsightFace models to {IF_MODELS_PATH}...")
            # Download basic models (1w3d65, 2d106det, det_10g, genderage, glintr100)
            base_url = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
            try:
                zip_path = os.path.join(INSIGHTFACE_DIR, "buffalo_l.zip")
                r = requests.get(base_url, stream=True, timeout=600)
                if r.status_code == 200:
                    with open(zip_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    log("InsightFace zip downloaded. Extracting...")
                    import zipfile
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(os.path.join(INSIGHTFACE_DIR, "models"))
                    os.remove(zip_path)
                    log("InsightFace models extracted.")
                else:
                     log(f"InsightFace download failed with status {r.status_code}")
            except Exception as e:
                log(f"InsightFace setup failed: {e}")
            
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
    # CLEANER PROMPT: Added POV/Wide Angle to match the reference style
    detail_prompt = ", (POV:1.2), (wide angle lens:1.2), (soft studio lighting, rim light:1.1), (natural skin texture, flush:0.8), (raw photo, dslr, 8k uhd:1.2), (spread legs:1.4), (legs wide open:1.4), (protruding vulva:1.3), (hands on legs:1.3)"
    
    # Save Pose Image if present
    pose_filename = "pose.png"
    if face_swap_image: # Using face_swap_image var for pose temporarily or add new logic
        # Logic to save pose image to /app/ComfyUI/input/pose.png
        pass

    # ControlNet Logic
    positive_condition_node = ["11", 0]
    negative_condition_node = ["12", 0]

    workflow = {
        "10": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": os.path.basename(CHECKPOINT_FILE)}
        },
        "19": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": os.path.basename(VAE_FILE)}
        },
        "13": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1}
        },
        # Clip Skip 2 for Pony
        "18": {
            "class_type": "CLIPSetLastLayer",
            "inputs": {
                "stop_at_clip_layer": -2,
                "clip": ["10", 1]
            }
        },
    }

    # Dynamic LoRA Chain
    # We build a chain of models and clips: Checkpoint -> LoRA1 -> LoRA2 -> ... -> TextEncode
    
    current_model = ["10", 0]
    current_clip = ["18", 0]
    
        # 1. Detail Slider
    if os.path.exists(LORA_DETAIL):
        workflow["100"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": os.path.basename(LORA_DETAIL),
                # DISABLED: 0.0 to fix skinny body/dirty skin issues
                "strength_model": 0.0,
                "strength_clip": 0.0,
                "model": current_model,
                "clip": current_clip
            }
        }
        current_model = ["100", 0]
        current_clip = ["100", 1]

    # 2. Cum Shot (Keep enabled but low)
    if os.path.exists(LORA_CUM):
        workflow["101"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": os.path.basename(LORA_CUM),
                "strength_model": 0.8,
                "strength_clip": 0.8,
                "model": current_model,
                "clip": current_clip
            }
        }
        current_model = ["101", 0]
        current_clip = ["101", 1]

    # 3. Expressions (DISABLED to fix face cloning/distortion)
    if os.path.exists(LORA_EXPRESSIONS):
        workflow["102"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": os.path.basename(LORA_EXPRESSIONS),
                "strength_model": 0.0,
                "strength_clip": 0.0,
                "model": current_model,
                "clip": current_clip
            }
        }
        current_model = ["102", 0]
        current_clip = ["102", 1]

    # Prompts connected to the last CLIP in the chain
    # Pony specific prefixes and negatives
    pony_prefix = "score_9, score_8_up, score_7_up, BREAK, "
    pony_negative = "score_4, score_5, score_6, source_pony, source_furry, text, watermark, blur, deformed, painting, cartoon, low quality, ugly, multiple views, multiple girls, clone, twin, anorexic, skinny, bad anatomy"

    workflow["11"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": pony_prefix + (prompt_text or "beautiful woman") + detail_prompt,
            "clip": current_clip 
        }
    }
    workflow["12"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": pony_negative,
            "clip": current_clip
        }
    }

    # Add ControlNet if image provided
    if face_swap_image: # Using face_swap_image as placeholder for now, ideally rename var
        # Save image
        try:
            os.makedirs("/app/ComfyUI/input", exist_ok=True)
            with open(f"/app/ComfyUI/input/{pose_filename}", "wb") as f:
                f.write(base64.b64decode(face_swap_image))
        except Exception as e:
            log(f"Failed to save pose image: {e}")

        workflow["50"] = {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": os.path.basename(CONTROLNET_FILE)}
        }
        workflow["51"] = {
            "class_type": "LoadImage",
            "inputs": {"image": pose_filename}
        }
        workflow["52"] = { # ControlNet Apply
            "class_type": "ControlNetApply",
            "inputs": {
                "conditioning": ["11", 0],
                "control_net": ["50", 0],
                "image": ["51", 0],
                "strength": 0.8
            }
        }
        positive_condition_node = ["52", 0]

    workflow["14"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "model": current_model, # Connect to last LoRA Model
                "positive": positive_condition_node,
                "negative": negative_condition_node,
                "latent_image": ["13", 0],
                "denoise": 1.0
            }
        }
    
    workflow["15"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["14", 0], "vae": ["19", 0]}
        }
    workflow["16"] = {
            "class_type": "SaveImage",
            "inputs": {"images": ["15", 0], "filename_prefix": "runpod_base_"}
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
                "model": current_model, # Connect to last LoRA Model
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["20", 0],
                # LOWER DENOISE: 0.65 -> 0.45 to preserve details without hallucinating
                "denoise": 0.45
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

import random

# ... (imports)

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
        # Tweaked CFG for better prompt adherence but keeping realism
        cfg = float(job_input.get("cfg", 6.0))
        # Better sampler for skin texture
        sampler_name = job_input.get("sampler_name", "dpmpp_2m") 
        scheduler = job_input.get("scheduler", "karras")
        
        # RANDOMIZE SEED if 0 or missing
        seed = int(job_input.get("seed", 0))
        if seed == 0:
            seed = random.randint(1, 18446744073709551615)
        
        negative_prompt = job_input.get("negative_prompt", "text, watermark, blur, deformed, painting, cartoon, low quality, ugly, multiple views, multiple girls, clone, twin, anorexic, skinny, bad anatomy")
        
        enable_highres = job_input.get("highres_fix", True)
        face_swap_img = job_input.get("face_image", None) # Base64 string if present
        controlnet_img = job_input.get("controlnet_image", None) # Base64 Pose image

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
