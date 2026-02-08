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
REACTOR_DIR = "/app/ComfyUI/models/reactor"

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

def download_file(url, path, headers=None):
    """Универсальный загрузчик с прогрессом"""
    try:
        r = requests.get(url, stream=True, timeout=600, headers=headers)
        if r.status_code == 200:
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (100 * 1024 * 1024) == 0:
                            log(f"Downloaded {downloaded / 1024 / 1024:.0f} MB / {total_size / 1024 / 1024:.0f} MB")
            log(f"Download complete: {path}")
            return True
        else:
            log(f"Download failed for {url} with status {r.status_code}")
            return False
    except Exception as e:
        log(f"Download error for {url}: {e}")
        return False

def ensure_models(custom_loras=None):
    """Минимальная проверка и быстрая загрузка модели, если отсутствует"""
    try:
        if not os.path.exists(MODELS_DIR):
            os.makedirs(MODELS_DIR, exist_ok=True)
        
        hf_token = os.environ.get("HF_TOKEN")
        hf_headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
        civitai_headers = {"User-Agent": "Mozilla/5.0"}

        # 1. Загрузка основного чекпоинта
        if not os.path.exists(CHECKPOINT_FILE) or os.path.getsize(CHECKPOINT_FILE) < 100 * 1024 * 1024:
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
            
            log("Downloading Pony Realism Checkpoint...")
            urls = [
                "https://huggingface.co/LyliaEngine/ponyRealism_v21MainVAE/resolve/main/ponyRealism_v21MainVAE.safetensors", 
                "https://civitai.com/api/download/models/534642?type=Model&format=SafeTensor"
            ]
            
            for url in urls:
                headers = hf_headers if "huggingface.co" in url else civitai_headers
                if download_file(url, CHECKPOINT_FILE, headers):
                    break

        # 2. Загрузка VAE
        if not os.path.exists(VAE_DIR):
            os.makedirs(VAE_DIR, exist_ok=True)
        # Стандартное имя для SDXL VAE
        VAE_FILE_ALT = os.path.join(VAE_DIR, "sdxl_vae.safetensors")
        if not os.path.exists(VAE_FILE_ALT):
            log(f"Downloading VAE...")
            vae_url = "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors"
            download_file(vae_url, VAE_FILE_ALT, hf_headers)

        # 3. Загрузка кастомных LoRA (для персонажей)
        actual_loras = []
        if custom_loras:
            if not os.path.exists(LORA_DIR): os.makedirs(LORA_DIR, exist_ok=True)
            for lora in custom_loras:
                name = lora.get("name")
                url = lora.get("url")
                if name and url:
                    url = url.strip().strip("'").strip("`").strip()
                    path = os.path.join(LORA_DIR, name)
                    if not os.path.exists(path):
                        log(f"Downloading custom LoRA: {name}...")
                        headers = hf_headers if "huggingface.co" in url else civitai_headers
                        if download_file(url, path, headers):
                            actual_loras.append(lora)
                    else:
                        actual_loras.append(lora)
        
        # Заставляем ComfyUI обновить список файлов
        try:
            requests.post(f"{COMFY_URL}/object_info", timeout=2)
        except:
            pass
            
        return actual_loras

        # 4. Базовые LoRA (Hinata, Cum, Detail, Expressions)
        # Отключаем пока они не нужны или битые ссылки
        # ...


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

def build_workflow(prompt_text, negative_prompt, width, height, seed, steps, cfg, sampler_name, scheduler, high_res_fix=True, face_swap_image=None, custom_loras=None):
    """
    Строит JSON Workflow для ComfyUI.
    high_res_fix=True включает 2-pass генерацию (Latent Upscale).
    face_swap_image: base64 string of face image (if provided)
    custom_loras: list of {"name": "...", "strength_model": 1.0, "strength_clip": 1.0}
    """
    # CLEANER PROMPT: Added POV/Wide Angle to match the reference style
    detail_prompt = ", (POV:1.2), (wide angle lens:1.2), (soft studio lighting, rim light:1.1), (natural skin texture, flush:0.8), (raw photo, dslr, 8k uhd:1.2), (spread legs:1.4), (legs wide open:1.4), (protruding vulva:1.3), (hands on legs:1.3)"
    
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
        "18": {
            "class_type": "CLIPSetLastLayer",
            "inputs": {
                "stop_at_clip_layer": -2,
                "clip": ["10", 1]
            }
        },
    }

    current_model = ["10", 0]
    current_clip = ["18", 0]
    
    # 1. Загрузка кастомных LoRA (Персонажи)
    if custom_loras:
        for i, lora in enumerate(custom_loras):
            node_id = f"200_{i}"
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora.get("name"),
                    "strength_model": lora.get("strength_model", 1.0),
                    "strength_clip": lora.get("strength_clip", 1.0),
                    "model": current_model,
                    "clip": current_clip
                }
            }
            current_model = [node_id, 0]
            current_clip = [node_id, 1]

    # 2. Базовые LoRA (например, Detail Slider)
    if os.path.exists(LORA_DETAIL):
        workflow["100"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": os.path.basename(LORA_DETAIL),
                "strength_model": 0.4,
                "strength_clip": 0.4,
                "model": current_model,
                "clip": current_clip
            }
        }
        current_model = ["100", 0]
        current_clip = ["100", 1]

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

    workflow["14"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "model": current_model,
            "positive": ["11", 0],
            "negative": ["12", 0],
            "latent_image": ["13", 0],
            "denoise": 1.0
        }
    }
    
    workflow["15"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["14", 0], "vae": ["19", 0]}
    }

    last_image_node = "15"

    # 3. High-Res Fix
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
                "model": current_model,
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["20", 0],
                "denoise": 0.45
            }
        }
        workflow["22"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["21", 0], "vae": ["19", 0]}
        }
        last_image_node = "22"

    # 4. Face Swap (ReActor)
    if face_swap_image:
        # Save face image to input folder
        face_filename = f"face_{seed}.png"
        try:
            os.makedirs("/app/ComfyUI/input", exist_ok=True)
            with open(f"/app/ComfyUI/input/{face_filename}", "wb") as f:
                f.write(base64.b64decode(face_swap_image))
            
            workflow["30"] = {
                "class_type": "LoadImage",
                "inputs": {"image": face_filename}
            }
            workflow["31"] = {
                "class_type": "ReActorFaceSwap",
                "inputs": {
                    "enabled": True,
                    "input_image": [last_image_node, 0],
                    "source_image": ["30", 0],
                    "face_index_source": 0,
                    "face_index_input": 0,
                    "face_model": "inswapper_128.onnx",
                    "detect_gender_source": "no",
                    "detect_gender_input": "no",
                    "upscale_by": 1,
                    "upscaler_name": "none",
                    "visibility": 1,
                    "codeformer_visibility": 0.5,
                    "codeformer_weight": 0.5
                }
            }
            last_image_node = "31"
        except Exception as e:
            log(f"FaceSwap node setup failed: {e}")

    workflow["1000"] = {
        "class_type": "SaveImage",
        "inputs": {"images": [last_image_node, 0], "filename_prefix": "uber_"}
    }

    return workflow

import shutil
import random

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

# Настройки путей
# Пытаемся определить корень проекта динамически
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOLUME_PATH = "/runpod-volume"
COMFY_PATH = os.path.join(PROJECT_ROOT, "ComfyUI")
MODELS_DIR = os.path.join(COMFY_PATH, "models")
CHECKPOINT_FILE = os.path.join(MODELS_DIR, "checkpoints", "PonyRealism_v2.1.safetensors")
LORA_DIR = os.path.join(MODELS_DIR, "loras")
OUTPUT_DIR = os.path.join(COMFY_PATH, "output")

def setup_volume_links():
    """Разворачивает окружение и ComfyUI на сетевой диск"""
    if not os.path.exists(VOLUME_PATH):
        log("Network Volume not attached. Using internal container storage.")
        # Если ComfyUI нет в папке проекта, скачиваем его туда
        if not os.path.exists(COMFY_PATH):
            log("Cloning ComfyUI to project root...")
            subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", COMFY_PATH], check=True)
        
        # Всегда проверяем зависимости при отсутствии Volume, так как это чистый контейнер
        log("Checking/Installing ComfyUI dependencies...")
        # Принудительно ставим numpy<2, так как 2.x ломает совместимость
        subprocess.run([sys.executable, "-m", "pip", "install", "numpy<2", "sqlalchemy", "alembic", "requests", "aiohttp", "pyyaml", "Pillow", "scipy", "tqdm", "psutil"], check=True)
        
        if os.path.exists(os.path.join(COMFY_PATH, "requirements.txt")):
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(COMFY_PATH, "requirements.txt")], check=True)
        return sys.executable

    # 1. Проверяем и устанавливаем PyTorch и зависимости на диск
    venv_path = os.path.join(VOLUME_PATH, "venv")
    bin_path = os.path.join(venv_path, "bin", "python")
    
    if not os.path.exists(bin_path):
        log("Environment not found on Volume. Installing dependencies (once)...")
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
        subprocess.run([bin_path, "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu121"], check=True)
        subprocess.run([bin_path, "-m", "pip", "install", "runpod", "requests", "transformers==4.38.2", "imagesize", "onnxruntime-gpu", "insightface"], check=True)

    # 2. Проверяем наличие ComfyUI на диске
    volume_comfy = os.path.join(VOLUME_PATH, "ComfyUI")
    if not os.path.exists(volume_comfy):
        log("Cloning ComfyUI to Volume...")
        subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", volume_comfy], check=True)
        
        # Установка нод
        nodes_dir = os.path.join(volume_comfy, "custom_nodes")
        subprocess.run(["git", "clone", "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git", os.path.join(nodes_dir, "ComfyUI-Impact-Pack")], check=True)
        subprocess.run(["git", "clone", "https://github.com/Gourieff/comfyui-reactor-node.git", os.path.join(nodes_dir, "comfyui-reactor-node")], check=True)
        
        # Установка зависимостей нод
        subprocess.run([bin_path, "-m", "pip", "install", "-r", os.path.join(nodes_dir, "ComfyUI-Impact-Pack/requirements.txt")], check=True)
        subprocess.run([bin_path, "-m", "pip", "install", "-r", os.path.join(nodes_dir, "comfyui-reactor-node/requirements.txt")], check=True)

    # 3. Создаем симлинк в папку проекта, чтобы код всегда искал в PROJECT_ROOT/ComfyUI
    if os.path.exists(COMFY_PATH) and not os.path.islink(COMFY_PATH):
        shutil.rmtree(COMFY_PATH)
    
    if not os.path.exists(COMFY_PATH):
        os.symlink(volume_comfy, COMFY_PATH)
        log("ComfyUI linked to Volume.")

    return bin_path

def handler(job):
    try:
        log(f"Received job: {job}")
        
        # Настраиваем связь с диском
        python_bin = setup_volume_links()
        
        # 1. Запуск ComfyUI (используя python с диска)
        if not check_comfy_status():
            log("Starting ComfyUI...")
            subprocess.Popen([python_bin, f"{COMFY_PATH}/main.py", "--listen", "0.0.0.0", "--port", "8188"])
            
            # Ждем запуска
            for _ in range(60):
                if check_comfy_status(): break
                time.sleep(2)
        clear_output_dir()
        job_input = job["input"]
        prompt_text = job_input.get("prompt", "")
        width = int(job_input.get("width", 1024))
        height = int(job_input.get("height", 1024))
        steps = int(job_input.get("steps", 25))
        cfg = float(job_input.get("cfg", 6.0))
        sampler_name = job_input.get("sampler_name", "dpmpp_2m") 
        scheduler = job_input.get("scheduler", "karras")
        
        # RANDOMIZE SEED
        seed = int(job_input.get("seed", 0))
        if seed == 0:
            seed = random.randint(1, 18446744073709551615)
        
        negative_prompt = job_input.get("negative_prompt", "score_4, score_5, score_6, source_pony, source_furry, text, watermark, blur, deformed, painting, cartoon, low quality, ugly, multiple views, multiple girls, clone, twin, anorexic, skinny, bad anatomy")
        
        enable_highres = job_input.get("highres_fix", True)
        face_swap_img = job_input.get("face_image", None) # Base64
        custom_loras = job_input.get("loras", []) # List of {"name": "...", "url": "...", "strength_model": 1.0}

        # 2. Проверка моделей (включая кастомные LoRA)
        custom_loras = ensure_models(custom_loras=custom_loras)

        # 3. Формируем API prompt (Workflow)
        prompt = build_workflow(
            prompt_text, negative_prompt, width, height, seed, steps, cfg, sampler_name, scheduler, 
            high_res_fix=enable_highres,
            face_swap_image=face_swap_img,
            custom_loras=custom_loras
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
