import runpod
import os
import json
import base64
import time
import requests
import glob
import subprocess
import shutil
import sys
import random
import zipfile
from io import BytesIO

# --- CONFIGURATION & PATHS ---
VERSION = "2.0-PRO-PIPELINE"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY_PATH = os.path.join(PROJECT_ROOT, "ComfyUI")
VOLUME_PATH = "/runpod-volume"
COMFY_URL = "http://127.0.0.1:8188"

# Model Directories
MODELS_DIR = os.path.join(COMFY_PATH, "models")
CHECKPOINTS_DIR = os.path.join(MODELS_DIR, "checkpoints")
VAE_DIR = os.path.join(MODELS_DIR, "vae")
LORA_DIR = os.path.join(MODELS_DIR, "loras")
CONTROLNET_DIR = os.path.join(MODELS_DIR, "controlnet")
UPSCALERS_DIR = os.path.join(MODELS_DIR, "upscale_models")
OUTPUT_DIR = os.path.join(COMFY_PATH, "output")

# Core Model Files
BASE_MODEL = os.path.join(CHECKPOINTS_DIR, "PonyRealism_v2.1.safetensors")
REFINER_MODEL = os.path.join(CHECKPOINTS_DIR, "sd_xl_refiner_1.0.safetensors")
VAE_FILE = os.path.join(VAE_DIR, "sdxl_vae.safetensors")

# Quality LoRAs (CivitAI / HF)
LORA_BODY = os.path.join(LORA_DIR, "human_body_realism_sdxl_lora.safetensors")
LORA_SKIN = os.path.join(LORA_DIR, "realistic_skin_texture_sdxl_lora.safetensors")
LORA_EBONY = os.path.join(LORA_DIR, "Ebony_Skin_Slider.safetensors")

# ControlNet Files
CONTROL_POSE = os.path.join(CONTROLNET_DIR, "controlnet-openpose-sdxl-1.0.safetensors")
CONTROL_DEPTH = os.path.join(CONTROLNET_DIR, "controlnet-depth-sdxl-1.0.safetensors")

# Upscaler
ULTRASHARP_FILE = os.path.join(UPSCALERS_DIR, "4x-UltraSharp.pth")

def log(message):
    print(f"[Handler] {message}", flush=True)

def check_comfy_status():
    """Wait for ComfyUI to be ready"""
    try:
        response = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def download_file(url, path, headers=None):
    """Download with progress logging"""
    if os.path.exists(path):
        return True
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        r = requests.get(url, stream=True, timeout=600, headers=headers)
        if r.status_code == 200:
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (200 * 1024 * 1024) == 0:
                            log(f"Downloaded {downloaded / 1024 / 1024:.0f} MB / {total_size / 1024 / 1024:.0f} MB")
            log(f"Download complete: {os.path.basename(path)}")
            return True
        log(f"Download failed for {url} (Status: {r.status_code})")
        return False
    except Exception as e:
        log(f"Download error: {e}")
        return False

def force_refresh():
    """Force ComfyUI to reload model lists"""
    try:
        requests.post(f"{COMFY_URL}/extra_model_paths", timeout=2)
        requests.post(f"{COMFY_URL}/refresh_checkpoints", timeout=2)
        requests.get(f"{COMFY_URL}/object_info", timeout=5)
    except: pass

def ensure_models(custom_loras=None):
    """Ensure all core and custom models are present"""
    hf_token = os.environ.get("HF_TOKEN")
    hf_headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    civit_headers = {"User-Agent": "ComfyUI-Serverless"}

    # 1. Core Models
    download_file("https://huggingface.co/Taras082498/PonyRealism/resolve/main/PonyRealism_v2.1.safetensors", BASE_MODEL, hf_headers)
    download_file("https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0.safetensors", REFINER_MODEL, hf_headers)
    download_file("https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors", VAE_FILE, hf_headers)

    # 2. ControlNet
    download_file("https://huggingface.co/diffusers/controlnet-depth-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors", CONTROL_DEPTH)
    download_file("https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors", CONTROL_POSE)

    # 3. Quality LoRAs
    download_file("https://civitai.com/api/download/models/215501", LORA_BODY, civit_headers)
    download_file("https://civitai.com/api/download/models/145823", LORA_SKIN, civit_headers)
    download_file("https://civitai.com/api/download/models/258213", LORA_EBONY, civit_headers)

    # 4. Upscaler
    download_file("https://huggingface.co/datasets/G1612/upscale_models/resolve/main/4x-UltraSharp.pth", ULTRASHARP_FILE)

    # 5. Custom LoRAs from Request
    actual_loras = []
    if custom_loras:
        for lora in custom_loras:
            name = lora.get("name")
            url = lora.get("url")
            if name and url:
                local_path = os.path.join(LORA_DIR, name)
                if download_file(url, local_path, hf_headers):
                    actual_loras.append({
                        "name": name,
                        "strength_model": lora.get("strength_model", 1.0),
                        "strength_clip": lora.get("strength_clip", 1.0)
                    })
    
    force_refresh()
    return actual_loras

def build_workflow(prompt_text, negative_prompt, width, height, seed, steps, cfg, sampler_name, scheduler, face_image=None, loras=None, job_id="uber"):
    """Professional SDXL Pipeline: Base -> Refiner -> Upscale"""
    workflow = {
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": os.path.basename(BASE_MODEL)}},
        "refiner": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": os.path.basename(REFINER_MODEL)}},
        "19": {"class_type": "VAELoader", "inputs": {"vae_name": os.path.basename(VAE_FILE)}},
        "13": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "18": {"class_type": "CLIPSetLastLayer", "inputs": {"stop_at_clip_layer": -2, "clip": ["10", 1]}},
        "upscale_model": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": os.path.basename(ULTRASHARP_FILE)}}
    }

    current_model = ["10", 0]
    current_clip = ["18", 0]

    # Apply Quality LoRAs (Matching "Идеальное тело" Plan)
    quality_loras = [
        {"name": os.path.basename(LORA_BODY), "str": 0.7}, # Plan: 0.6 - 0.8
        {"name": os.path.basename(LORA_SKIN), "str": 0.6}, # Plan: 0.5 - 0.7
        {"name": os.path.basename(LORA_EBONY), "str": 0.8} # Plan: 0.7 - 0.9
    ]
    for i, ql in enumerate(quality_loras):
        node_id = f"ql_{i}"
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": ql["name"], "strength_model": ql["str"], "strength_clip": ql["str"],
                "model": current_model, "clip": current_clip
            }
        }
        current_model = [node_id, 0]
        current_clip = [node_id, 1]

    # Apply Custom LoRAs
    if loras:
        for i, cl in enumerate(loras):
            node_id = f"cl_{i}"
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": cl["name"], "strength_model": cl["strength_model"], "strength_clip": cl["strength_clip"],
                    "model": current_model, "clip": current_clip
                }
            }
            current_model = [node_id, 0]
            current_clip = [node_id, 1]

    # Text Encoding
    workflow["11"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_text, "clip": current_clip}}
    workflow["12"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": current_clip}}

    last_pos = ["11", 0]

    # ControlNet (Pose & Depth)
    if face_image:
        workflow["input_img"] = {"class_type": "ETN_LoadImageBase64", "inputs": {"base64_data": face_image}}
        
        # 1. OpenPose (Скелет)
        workflow["cn_pose"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": os.path.basename(CONTROL_POSE)}}
        workflow["apply_pose"] = {
            "class_type": "ControlNetApply",
            "inputs": {"strength": 1.0, "conditioning": last_pos, "control_net": ["cn_pose", 0], "image": ["input_img", 0]}
        }
        last_pos = ["apply_pose", 0]

        # 2. Depth (Объем и формы)
        workflow["cn_depth"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": os.path.basename(CONTROL_DEPTH)}}
        workflow["apply_depth"] = {
            "class_type": "ControlNetApply",
            "inputs": {"strength": 0.6, "conditioning": last_pos, "control_net": ["cn_depth", 0], "image": ["input_img", 0]}
        }
        last_pos = ["apply_depth", 0]

    # KSampler (Base)
    workflow["14"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler_name, "scheduler": scheduler,
            "model": current_model, "positive": last_pos, "negative": ["12", 0],
            "latent_image": ["13", 0], "denoise": 1.0
        }
    }

    # KSampler (Refiner)
    workflow["21"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed, "steps": 20, "cfg": cfg,
            "sampler_name": sampler_name, "scheduler": scheduler,
            "model": ["refiner", 0], "positive": ["11", 0], "negative": ["12", 0],
            "latent_image": ["14", 0], "denoise": 0.25 # Plan: 0.2 - 0.35
        }
    }

    # Decode & Upscale
    workflow["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["21", 0], "vae": ["19", 0]}}
    workflow["upscale"] = {
        "class_type": "ImageUpscaleWithModel",
        "inputs": {"upscale_model": ["upscale_model", 0], "image": ["decode", 0]}
    }
    workflow["1000"] = {"class_type": "SaveImage", "inputs": {"images": ["upscale", 0], "filename_prefix": f"{job_id}_"}}

    return workflow

def get_latest_image(job_id):
    """Find the output image for this specific job"""
    pattern = os.path.join(OUTPUT_DIR, f"{job_id}_*.png")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if files:
        with open(files[0], "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return None

def setup_env():
    """Clone ComfyUI and install dependencies if missing"""
    if not os.path.exists(COMFY_PATH) or not os.path.exists(os.path.join(COMFY_PATH, "main.py")):
        log("Clean installing ComfyUI...")
        if os.path.exists(COMFY_PATH): shutil.rmtree(COMFY_PATH)
        subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", COMFY_PATH], check=True)
        # Force compatible versions and install missing Comfy-Org dependencies
        subprocess.run([sys.executable, "-m", "pip", "install", "numpy<2.0.0", "comfy-aimdo>=0.1.7", "torchsde", "einops", "transformers>=4.25.1", "av", "kornia", "spandrel", "opencv-python-headless==4.8.1.78", "requests", "aiohttp", "Pillow", "scipy", "tqdm"], check=True)
        # REMOVED: pip install -e . (Caused Multiple top-level packages error)
    
    def download_zip(url, target_dir, folder_name):
        if os.path.exists(target_dir): return
        log(f"Installing {folder_name} via ZIP...")
        try:
            # Try different possible branch names for ZIP
            for branch in ["main", "master", "Main", "Master"]:
                test_url = url.replace("heads/main.zip", f"heads/{branch}.zip")
                r = requests.get(test_url, timeout=30)
                if r.status_code == 200:
                    import zipfile
                    from io import BytesIO
                    with zipfile.ZipFile(BytesIO(r.content)) as zip_ref:
                        zip_ref.extractall(os.path.join(COMFY_PATH, "custom_nodes"))
                    
                    extracted_folders = [d for d in os.listdir(os.path.join(COMFY_PATH, "custom_nodes")) if d.lower().startswith(folder_name.lower())]
                    for folder in extracted_folders:
                        old_path = os.path.join(COMFY_PATH, "custom_nodes", folder)
                        new_path = os.path.join(COMFY_PATH, "custom_nodes", folder_name)
                        if not os.path.exists(new_path):
                            os.rename(old_path, new_path)
                            log(f"Successfully installed {folder_name}")
                    return
            log(f"Failed to download ZIP for {folder_name} after trying all branches.")
        except Exception as e:
            log(f"Error installing {folder_name}: {e}")

    # Install nodes via ZIP
    download_zip("https://github.com/ltdrdata/ComfyUI-Impact-Pack/archive/refs/heads/main.zip", 
                 os.path.join(COMFY_PATH, "custom_nodes/ComfyUI-Impact-Pack"), "ComfyUI-Impact-Pack")
    
    download_zip("https://github.com/cubiq/ComfyUI_Essentials/archive/refs/heads/main.zip", 
                 os.path.join(COMFY_PATH, "custom_nodes/comfyui-essentials"), "comfyui-essentials")

def handler(job):
    try:
        job_id = job.get("id", "uber")
        job_input = job.get("input", {})
        log(f"--- STARTING JOB {job_id} ---")
        log(f"--- PIPELINE VERSION: {VERSION} ---")

        setup_env()

        # Add ComfyUI to path to ensure modules are findable
        if COMFY_PATH not in sys.path: sys.path.insert(0, COMFY_PATH)
        
        # Start ComfyUI if not running
        if not check_comfy_status():
            log("Launching ComfyUI...")
            subprocess.Popen([sys.executable, os.path.join(COMFY_PATH, "main.py"), "--listen", "0.0.0.0", "--port", "8188"])
            for _ in range(30):
                if check_comfy_status(): break
                time.sleep(2)

        # Download Models
        active_loras = ensure_models(custom_loras=job_input.get("loras", []))

        # Build Workflow
        workflow = build_workflow(
            prompt_text=job_input.get("prompt", ""),
            negative_prompt=job_input.get("negative_prompt", ""),
            width=job_input.get("width", 1024),
            height=job_input.get("height", 1024),
            seed=job_input.get("seed", random.randint(1, 1e15)),
            steps=job_input.get("steps", 35),
            cfg=job_input.get("cfg", 5.0),
            sampler_name=job_input.get("sampler_name", "dpmpp_2m"),
            scheduler=job_input.get("scheduler", "karras"),
            face_image=job_input.get("face_image"),
            loras=active_loras,
            job_id=job_id
        )

        # Queue Prompt
        response = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow, "client_id": job_id})
        if response.status_code != 200:
            return {"error": f"ComfyUI Error: {response.text}"}

        # Wait for Result
        deadline = time.time() + 600
        while time.time() < deadline:
            img = get_latest_image(job_id)
            if img: return {"status": "success", "image_base64": img}
            time.sleep(2)

        return {"error": "Generation timeout"}

    except Exception as e:
        import traceback
        return {"error": f"{str(e)}\n{traceback.format_exc()}"}

runpod.serverless.start({"handler": handler})
