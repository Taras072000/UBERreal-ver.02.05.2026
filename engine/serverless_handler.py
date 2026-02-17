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

def check_comfy_status():
    """Wait for ComfyUI to be ready"""
    try:
        response = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def force_refresh():
    """Force ComfyUI to reload model lists"""
    try:
        requests.post(f"{COMFY_URL}/extra_model_paths", timeout=2)
        requests.post(f"{COMFY_URL}/refresh_checkpoints", timeout=2)
        requests.get(f"{COMFY_URL}/object_info", timeout=5)
    except: pass

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
# BASE_MODEL = os.path.join(CHECKPOINTS_DIR, "sd_xl_base_1.0.safetensors")
BASE_MODEL = os.path.join(CHECKPOINTS_DIR, "URPMPonyXL-HybridV1.safetensors") # Switched to URPM PonyXL
REFINER_MODEL = os.path.join(CHECKPOINTS_DIR, "sd_xl_refiner_1.0.safetensors")
VAE_FILE = os.path.join(VAE_DIR, "sdxl_vae.safetensors")

# Quality LoRAs (CivitAI / HF)
LORA_BODY = os.path.join(LORA_DIR, "human_body_realism_sdxl_lora.safetensors")
LORA_SKIN = os.path.join(LORA_DIR, "realistic_skin_texture_sdxl_lora.safetensors")
LORA_EBONY = os.path.join(LORA_DIR, "Ebony_Skin_Slider.safetensors")
LORA_LUSTIFY = os.path.join(LORA_DIR, "LUSTIFY_SDXL_v1.safetensors")
LORA_DEEPTHROAT = os.path.join(LORA_DIR, "DeepThroatXL_v1.safetensors")
LORA_AMATEUR = os.path.join(LORA_DIR, "PonyAmateur_v2.safetensors")
LORA_PERFECT_FACIAL = os.path.join(LORA_DIR, "PerfectFacial_Pony_v1.safetensors")
LORA_BETTERNUDES = os.path.join(LORA_DIR, "PhotoRealBetterNudes_v3.safetensors")
LORA_FUTA = os.path.join(LORA_DIR, "RealisticFutaTrans_v1.safetensors")
LORA_BUTTPLUG = os.path.join(LORA_DIR, "ButtPlugUnderThong_v075.safetensors")
LORA_ANAL_MISSIONARY = os.path.join(LORA_DIR, "AnalSideMissionary_Pony_v1.safetensors")
LORA_ANAL_ABUSE = os.path.join(LORA_DIR, "AnalAbuse_v1.safetensors")
LORA_PERFECT_ANAL = os.path.join(LORA_DIR, "PerfectAnal_Pony_v1.safetensors")
LORA_PERFECT_BREASTS = os.path.join(LORA_DIR, "PerfectBreasts_v2.safetensors")
LORA_ULTRAREAL_BREASTS = os.path.join(LORA_DIR, "UltraRealBreastDetailer_v2.safetensors")
LORA_REALISM_YOGI = os.path.join(LORA_DIR, "RealismLora_v3_lite.safetensors")
LORA_BETTER_CUM = os.path.join(LORA_DIR, "BetterCum_Pony_v1.safetensors")
LORA_REALISTIC_SKIN_PONY = os.path.join(LORA_DIR, "Realistic_Skin_Pony_v0.1beta.safetensors")
LORA_DETAILED_EYES = os.path.join(LORA_DIR, "DetailedEyes_XL_v3.safetensors")
LORA_DYNAMIC_POSES = os.path.join(LORA_DIR, "DynamicPoses_PonyXL_v1.safetensors")

# IPAdapter & CLIP Vision
IPADAPTER_DIR = os.path.join(MODELS_DIR, "ipadapter")
CLIP_VISION_DIR = os.path.join(MODELS_DIR, "clip_vision")
IPADAPTER_MODEL = os.path.join(IPADAPTER_DIR, "ip-adapter-plus-face_sdxl_vit-h.safetensors")
CLIP_VISION_MODEL = os.path.join(CLIP_VISION_DIR, "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")

# ControlNet Files
CONTROL_POSE = os.path.join(CONTROLNET_DIR, "controlnet-openpose-sdxl-1.0.safetensors")
CONTROL_DEPTH = os.path.join(CONTROLNET_DIR, "controlnet-depth-sdxl-1.0.safetensors")

# Upscaler
ULTRASHARP_FILE = os.path.join(UPSCALERS_DIR, "4x-UltraSharp.pth")

# InsightFace (ReActor)
INSIGHTFACE_DIR = os.path.join(MODELS_DIR, "insightface")
INSWAPPER_FILE = os.path.join(INSIGHTFACE_DIR, "inswapper_128.onnx")

def log(message):
    print(f"[Handler] {message}", flush=True)

def download_file(url, path, headers=None):
    """Download with progress logging and smart auth"""
    if os.path.exists(path):
        return True
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Add auth headers if needed
        if "huggingface.co" in url and not headers:
            token = os.environ.get("HF_TOKEN")
            if token: headers = {"Authorization": f"Bearer {token}"}
            
        if "civitai.com" in url and not headers:
            token = os.environ.get("CIVITAI_API_TOKEN")
            if not token:
                # Fallback to the provided key if env var is missing
                token = "f92a9d20b490944390a3f6908fc43f35"
            if token: headers = {"Authorization": f"Bearer {token}"}
            
        r = requests.get(url, stream=True, timeout=600, headers=headers)
        if r.status_code == 200:
            # Check for HTML response (login page or error)
            content_type = r.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                log(f"Error: URL returned HTML (likely login page or 404): {url}")
                return False
                
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

def ensure_models(custom_loras=None):
    """Ensure all core and custom models are present"""
    # Пути к моделям
    LORA_DIR = os.path.join(COMFY_PATH, "models/loras")
    CHECKPOINTS_DIR = os.path.join(COMFY_PATH, "models/checkpoints")
    UPSCALE_DIR = os.path.join(COMFY_PATH, "models/upscale_models")
    VAE_DIR = os.path.join(COMFY_PATH, "models/vae")
    CONTROLNET_DIR = os.path.join(COMFY_PATH, "models/controlnet") # Correct path for controlnet

    # 1. Основные модели (Public Mirrors - Reliable)
    # SDXL Base 1.0 (Public HF) - Standard SDXL for testing
    download_file("https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors", os.path.join(CHECKPOINTS_DIR, "sd_xl_base_1.0.safetensors"))
    
    # URPM PonyXL-Hybrid (Requested by User) - Using Civitai API to ensure correct version
    # Model ID: 790652, Version ID: 923681
    download_file("https://civitai.com/api/download/models/923681", os.path.join(CHECKPOINTS_DIR, "URPMPonyXL-HybridV1.safetensors"))

    # SDXL Refiner removed for compatibility
    
    # VAE (Public HF) - Renaming to match workflow expectation
    download_file("https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors", os.path.join(VAE_DIR, "sdxl_vae.safetensors"))

    # Upscaler (Public HF)
    download_file("https://huggingface.co/uwg/upscaler/resolve/main/ESRGAN/4x-UltraSharp.pth", os.path.join(UPSCALE_DIR, "4x-UltraSharp.pth"))
    
    # ControlNet (Public HF)
    download_file("https://huggingface.co/diffusers/controlnet-depth-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors", os.path.join(CONTROLNET_DIR, "controlnet-depth-sdxl-1.0.safetensors"))
    download_file("https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors", os.path.join(CONTROLNET_DIR, "OpenPoseXL2.safetensors"))

    # 2. LoRAs (Идеальное тело) - Public Links & Fixed Names
    # Anatomy
    download_file("https://civitai.com/api/download/models/135867", os.path.join(LORA_DIR, "human_body_realism_sdxl_lora.safetensors"))
    # Skin (Using reliable alternative link from HF Mirror)
    # Old broken link: https://civitai.com/api/download/models/122359
    download_file("https://huggingface.co/AiWise/epiCPhoto-XL-LoRA-Derp2/resolve/main/LoRA-RealisticSkinTextureStyle-SDXL_v4.safetensors", os.path.join(LORA_DIR, "realistic_skin_texture_sdxl_lora.safetensors"))
    # Ebony Skin (PonyXL/SDXL compatible) - Requires Civitai Token or Manual Download
    # download_file("https://civitai.com/api/download/models/1106176", os.path.join(LORA_DIR, "StS_Skin_Tone_Slider.safetensors"))

    # LUSTIFY LoRA (Requested by User) - Requires Civitai Token
    download_file("https://civitai.com/api/download/models/1627770", os.path.join(LORA_DIR, "LUSTIFY_SDXL_v1.safetensors"))

    # DeepThroat LoRA
    download_file("https://civitai.com/api/download/models/309802", os.path.join(LORA_DIR, "DeepThroatXL_v1.safetensors"))

    # Realism Yogi LoRA
    download_file("https://civitai.com/api/download/models/1098033", os.path.join(LORA_DIR, "RealismLora_v3_lite.safetensors"))

    # Amateur LoRA
    download_file("https://civitai.com/api/download/models/717403", os.path.join(LORA_DIR, "PonyAmateur_v2.safetensors"))

    # Perfect Facial - Pony - V1 (ID: 1044499)
    download_file("https://civitai.com/api/download/models/1044499", os.path.join(LORA_DIR, "PerfectFacial_Pony_v1.safetensors"))

    # PhotoReal BetterNudes / NSFW - v3.0 (ID: 2474435)
    download_file("https://civitai.com/api/download/models/2474435", os.path.join(LORA_DIR, "PhotoRealBetterNudes_v3.safetensors"))

    # Realistic Futa/Trans Dick Pic - v1.0 (ID: 1496391)
    download_file("https://civitai.com/api/download/models/1496391", os.path.join(LORA_DIR, "RealisticFutaTrans_v1.safetensors"))

    # Butt Plug Under Thong v0.75 (ID: 893303)
    download_file("https://civitai.com/api/download/models/893303", os.path.join(LORA_DIR, "ButtPlugUnderThong_v075.safetensors"))

    # Anal Side Missionary (ID: 168340 -> Ver: 981838)
    download_file("https://civitai.com/api/download/models/981838", os.path.join(LORA_DIR, "AnalSideMissionary_Pony_v1.safetensors"))

    # Anal Abuse (ID: 709218 -> Ver: 793284)
    download_file("https://civitai.com/api/download/models/793284", os.path.join(LORA_DIR, "AnalAbuse_v1.safetensors"))

    # Perfect Anal Pony (ID: 639310 -> Ver: 715046)
    download_file("https://civitai.com/api/download/models/715046", os.path.join(LORA_DIR, "PerfectAnal_Pony_v1.safetensors"))

    # Perfect Breasts Pony (ID: 1621732 -> Ver: 1987668)
    download_file("https://civitai.com/api/download/models/1987668", os.path.join(LORA_DIR, "PerfectBreasts_v2.safetensors"))

    # UltraReal Breast & Nipple Detailer (ID: 1259365 -> Ver: 2429108)
    download_file("https://civitai.com/api/download/models/2429108", os.path.join(LORA_DIR, "UltraRealBreastDetailer_v2.safetensors"))

    # Better Cum - Pony - v1.0 (ID: 559962)
    download_file("https://civitai.com/api/download/models/559962", os.path.join(LORA_DIR, "BetterCum_Pony_v1.safetensors"))

    # Realistic Skin for Pony - v0.1beta (ID: 638628)
    download_file("https://civitai.com/api/download/models/638628", os.path.join(LORA_DIR, "Realistic_Skin_Pony_v0.1beta.safetensors"))

    # Detailed Eyes XL - v3.0 (ID: 120723)
    download_file("https://civitai.com/api/download/models/120723", os.path.join(LORA_DIR, "DetailedEyes_XL_v3.safetensors"))

    # Dynamic Poses Slider PONYXL (ID: 438059 -> Version ID: 489439)
    # Allows for more dynamic and extreme poses
    download_file("https://civitai.com/api/download/models/489439", os.path.join(LORA_DIR, "DynamicPoses_PonyXL_v1.safetensors"))

    # --- IPAdapter & CLIP Vision ---
    # IP-Adapter Plus Face SDXL (ViT-H) - Best for likeness
    download_file("https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors", IPADAPTER_MODEL)
    
    # CLIP Vision (ViT-H) - Required for IPAdapter Plus
    download_file("https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/sdxl_model.safetensors", CLIP_VISION_MODEL) # Note: Often named like this or CLIP-ViT-H-14... using standard HF path

    # 5. Custom LoRAs from Request
    actual_loras = []
    
    # Ensure Quality LoRAs exist (but don't add to custom list to avoid duplication)
    quality_loras_check = [
        {"name": "human_body_realism_sdxl_lora.safetensors"},
        {"name": "realistic_skin_texture_sdxl_lora.safetensors"},
        {"name": "Ebony_Skin_Slider.safetensors"},
        {"name": "LUSTIFY_SDXL_v1.safetensors"}
    ]
    
    for ql in quality_loras_check:
        if not os.path.exists(os.path.join(LORA_DIR, ql["name"])):
            log(f"Warning: Quality LoRA missing: {ql['name']}")

    if custom_loras:
        for lora in custom_loras:
            name = lora.get("name")
            url = lora.get("url")
            local_path = os.path.join(LORA_DIR, name)
            
            # 1. Check if exists locally (Volume)
            if os.path.exists(local_path):
                 actual_loras.append({
                        "name": name,
                        "strength_model": lora.get("strength_model", 1.0),
                        "strength_clip": lora.get("strength_clip", 1.0)
                    })
                 continue

            # 2. Download if missing
            if name and url:
                if download_file(url, local_path):
                    actual_loras.append({
                        "name": name,
                        "strength_model": lora.get("strength_model", 1.0),
                        "strength_clip": lora.get("strength_clip", 1.0)
                    })
    
    force_refresh()
    return actual_loras

def build_workflow(prompt_text, negative_prompt, width, height, seed, steps, cfg, sampler_name, scheduler, controlnet_image=None, face_swap_image=None, identity_strength=0.6, loras=None, job_id="uber"):
    """Professional SDXL Pipeline: Base 1.0 -> Upscale (Standard SDXL for compatibility testing)"""
    workflow = {
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": os.path.basename(BASE_MODEL)}},
        # Refiner removed
        "19": {"class_type": "VAELoader", "inputs": {"vae_name": os.path.basename(VAE_FILE)}},
        "13": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "18": {"class_type": "CLIPSetLastLayer", "inputs": {"stop_at_clip_layer": -2, "clip": ["10", 1]}},
        "upscale_model": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": os.path.basename(ULTRASHARP_FILE)}}
    }

    current_model = ["10", 0]
    current_clip = ["18", 0]

    # Apply Quality LoRAs (Matching "Идеальное тело" Plan)
    # NOTE: Ebony Skin re-enabled (Refiner was the issue, not LoRA)
    quality_loras = [
        {"name": "RealismLora_v3_lite.safetensors", "str": 0.8}, # Reduced slightly to mix better
        {"name": "Realistic_Skin_Pony_v0.1beta.safetensors", "str": 0.8}, # New Pony Skin
        {"name": "DetailedEyes_XL_v3.safetensors", "str": 0.8}, # New Detailed Eyes
        {"name": "DynamicPoses_PonyXL_v1.safetensors", "str": 1.0}, # New Dynamic Poses
        {"name": "human_body_realism_sdxl_lora.safetensors", "str": 0.5}, # Reduced
        {"name": "Ebony_Skin_Slider.safetensors", "str": 0.8} # Re-enabled (File exists)
    ]
    
    for i, ql in enumerate(quality_loras):
        # Skip if file missing
        if not os.path.exists(os.path.join(LORA_DIR, ql["name"])):
            continue
            
        node_id = f"ql_{i}"
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": ql["name"],
                "strength_model": ql["str"],
                "strength_clip": ql["str"],
                "model": current_model,
                "clip": ["18", 0] # Base CLIP
            }
        }
        current_model = [node_id, 0]
        # current_clip = [node_id, 1]

    # Apply Custom LoRAs
    if loras:
        for i, cl in enumerate(loras):
            node_id = f"cl_{i}"
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": cl["name"],
                    "strength_model": cl["strength_model"],
                    "strength_clip": cl["strength_clip"],
                    "model": current_model,
                    "clip": ["18", 0] # Base CLIP
                }
            }
            current_model = [node_id, 0]
            # current_clip = [node_id, 1]

    # Text Encoding
    workflow["11"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_text, "clip": current_clip}}
    workflow["12"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": current_clip}}

    last_pos = ["11", 0]

    # 3. IPAdapter (Identity Injection) - BEFORE KSampler
    if face_swap_image:
        # Load CLIP Vision
        workflow["clip_vision"] = {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": "sdxl_model.safetensors"} # Filename from download
        }
        
        # Load IPAdapter Model
        workflow["ipadapter_model"] = {
            "class_type": "IPAdapterModelLoader",
            "inputs": {"ipadapter_file": "ip-adapter-plus-face_sdxl_vit-h.safetensors"}
        }
        
        # Load Image for IPAdapter
        workflow["input_face_source"] = {"class_type": "ETN_LoadImageBase64", "inputs": {"base64_data": face_swap_image}}
        
        # Identity Strength (Default 0.5)
        ip_weight = identity_strength

        workflow["ipadapter_apply"] = {
            "class_type": "IPAdapterApply",
            "inputs": {
                "ipadapter": ["ipadapter_model", 0],
                "clip_vision": ["clip_vision", 0],
                "image": ["input_face_source", 0],
                "model": current_model,
                "weight": ip_weight,
                "noise": 0.0, 
                "start_at": 0.0,
                "end_at": 1.0,
                "weight_type": "standard"
            }
        }
        current_model = ["ipadapter_apply", 0]
    
    # ControlNet (Pose & Depth)
    if controlnet_image:
        workflow["input_pose_img"] = {"class_type": "ETN_LoadImageBase64", "inputs": {"base64_data": controlnet_image}}
        
        # 1. OpenPose (Скелет)
        if os.path.exists(CONTROL_POSE):
            workflow["cn_pose"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": os.path.basename(CONTROL_POSE)}}
            workflow["apply_pose"] = {
                "class_type": "ControlNetApply",
                "inputs": {"strength": 1.0, "conditioning": last_pos, "control_net": ["cn_pose", 0], "image": ["input_pose_img", 0]}
            }
            last_pos = ["apply_pose", 0]
        else:
            log(f"ControlNet Pose missing: {CONTROL_POSE}")

        # 2. Depth (Объем и формы)
        if os.path.exists(CONTROL_DEPTH):
            workflow["cn_depth"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": os.path.basename(CONTROL_DEPTH)}}
            workflow["apply_depth"] = {
                "class_type": "ControlNetApply",
                "inputs": {"strength": 0.6, "conditioning": last_pos, "control_net": ["cn_depth", 0], "image": ["input_pose_img", 0]}
            }
            last_pos = ["apply_depth", 0]
        else:
            log(f"ControlNet Depth missing: {CONTROL_DEPTH}")

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

    # Decode (Directly from Base KSampler 14)
    workflow["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["19", 0]}}
    
    last_image_node = ["decode", 0]
    
    # ReActor Face Swap
    if face_swap_image:
        workflow["input_face_swap"] = {"class_type": "ETN_LoadImageBase64", "inputs": {"base64_data": face_swap_image}}
        
        workflow["reactor"] = {
            "class_type": "ReActorFastFaceSwap",
            "inputs": {
                "enabled": True,
                "swap_model": "inswapper_128.onnx",
                "facedetection": "retinaface_resnet50",
                "face_restore_model": "codeformer-v0.1.0.pth", # Optional: can be none if not installed, but usually comes with ReActor
                "face_restore_visibility": 1.0,
                "codeformer_weight": 0.7, # Reduced to 0.7 for better likeness (less plastic)
                "detect_gender_input": "female", # Target only females (avoid swapping male/penis owners)
                "detect_gender_source": "female", # Assume source is female
                "input_faces_index": "0",
                "source_faces_index": "0",
                "console_log_level": 2,
                "source_image": ["input_face_swap", 0],
                "input_image": last_image_node
            }
        }
        last_image_node = ["reactor", 0]
    
    # Upscale REMOVED for testing (Image too large for response)
    # workflow["upscale"] = {
    #     "class_type": "ImageUpscaleWithModel",
    #     "inputs": {"upscale_model": ["upscale_model", 0], "image": ["decode", 0]}
    # }
    
    workflow["1000"] = {"class_type": "SaveImage", "inputs": {"images": last_image_node, "filename_prefix": f"result_{job_id}"}}

    return workflow

def get_latest_image(job_id, min_timestamp=0):
    """Find the output image created AFTER min_timestamp"""
    import io
    from PIL import Image

    # Helper to process image file
    def process_image(path):
        try:
            with Image.open(path) as img:
                # Convert to RGB (in case of RGBA)
                if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
                
                # Resize if too large (max 2048x2048)
                if img.width > 2048 or img.height > 2048:
                    img.thumbnail((2048, 2048))
                
                # Save as JPEG to memory
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=85)
                return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as e:
            log(f"Error processing image {path}: {e}")
            return None

    # 1. Try filename_prefix pattern
    pattern = os.path.join(OUTPUT_DIR, f"result_{job_id}_*.png")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if files:
        # Check if file is new enough
        if os.path.getmtime(files[0]) > min_timestamp:
            return process_image(files[0])
    
    # 2. Try simple wildcard search (fallback)
    pattern_all = os.path.join(OUTPUT_DIR, "*.png")
    files_all = sorted(glob.glob(pattern_all), key=os.path.getmtime, reverse=True)
    if files_all:
         # Only pick if recent (last 30s) and newer than start time
         mtime = os.path.getmtime(files_all[0])
         if time.time() - mtime < 30 and mtime > min_timestamp:
             return process_image(files_all[0])

    return None

def setup_env():
    """Clone ComfyUI and install dependencies if missing"""
    if not os.path.exists(COMFY_PATH) or not os.path.exists(os.path.join(COMFY_PATH, "main.py")):
        log("Clean installing ComfyUI...")
        if os.path.exists(COMFY_PATH): shutil.rmtree(COMFY_PATH)
        subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", COMFY_PATH], check=True)
        # 1. Install official ComfyUI requirements first (Critical for frontend)
    # Using --no-cache-dir to prevent OOM on small containers
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", os.path.join(COMFY_PATH, "requirements.txt")], check=True)
    
    # 2. Force install comfy-ui-client-frontend to fix missing metadata error
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "comfy-ui-client"], check=True)
    
    # 3. Force compatible versions and install missing system dependencies
    # NOTE: Using standard diffusers (0.29.0+) from PyPI is safer/faster than git source
    # Downgrading to 0.29.0 to ensure compatibility with older PyTorch versions in RunPod base images
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "numpy<2.0.0", "comfy-aimdo>=0.1.7", "torchsde", "einops", "transformers>=4.25.1", "av", "kornia", "spandrel", "piexif", "segment_anything", "opencv-python-headless==4.8.1.78", "requests", "aiohttp", "Pillow", "scipy", "tqdm", "diffusers>=0.29.0", "accelerate", "peft", "bitsandbytes"], check=True)
        # REMOVED: pip install -e . (Caused Multiple top-level packages error)
    
    # 4. Training Script Download REMOVED per user request

    
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

    download_zip("https://github.com/Gourieff/ComfyUI-ReActor/archive/refs/heads/main.zip",
                 os.path.join(COMFY_PATH, "custom_nodes/comfyui-reactor-node"), "comfyui-reactor-node")
                 
    # Ensure InsightFace model exists
    if not os.path.exists(INSWAPPER_FILE):
        # Using huggingface mirror which is more reliable than facefusion assets (often 404)
        download_file("https://huggingface.co/eziorry/inswapper_128.onnx/resolve/main/inswapper_128.onnx", INSWAPPER_FILE)

def upload_file_robust(file_path, file_name):
    """Upload file to multiple services with fallback"""
    import requests
    
    # 1. Try transfer.sh
    try:
        log(f"Uploading {file_name} to transfer.sh...")
        with open(file_path, 'rb') as f:
            r = requests.put(f"https://transfer.sh/{file_name}", data=f, timeout=120)
            if r.status_code == 200:
                url = r.text.strip()
                if url.startswith("http"): return url
    except Exception as e:
        log(f"transfer.sh failed: {e}")

    # 2. Try tmpfiles.org
    try:
        log(f"Uploading {file_name} to tmpfiles.org...")
        with open(file_path, 'rb') as f:
            files = {'file': (file_name, f)}
            r = requests.post('https://tmpfiles.org/api/v1/upload', files=files, timeout=120)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "success":
                    url = data["data"]["url"]
                    return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as e:
        log(f"tmpfiles.org failed: {e}")
        
    # 3. Try file.io (expires after 1 download, good for secure transfer)
    try:
        log(f"Uploading {file_name} to file.io...")
        with open(file_path, 'rb') as f:
            files = {'file': (file_name, f)}
            r = requests.post('https://file.io', files=files, timeout=120)
            if r.status_code == 200:
                data = r.json()
                if data.get("success"): return data.get("link")
    except Exception as e:
        log(f"file.io failed: {e}")
        
    return ""

def log_system_stats():
    """Log disk and memory usage"""
    try:
        total, used, free = shutil.disk_usage("/")
        log(f"Disk Usage: Total={total//(2**30)}GB, Used={used//(2**30)}GB, Free={free//(2**30)}GB")
        
        # Memory
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
            for line in meminfo.splitlines():
                if "MemTotal" in line or "MemAvailable" in line:
                    log(line)
    except: pass

def handler(job):
    try:
        job_id = job.get("id", "uber")
        job_input = job.get("input", {})
        log(f"--- STARTING JOB {job_id} ---")
        
        # Default: Generation
        log(f"--- PIPELINE VERSION: {VERSION} ---")
        
        # Debug: Check output dir
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            log(f"Created OUTPUT_DIR: {OUTPUT_DIR}")
        else:
            log(f"OUTPUT_DIR exists: {OUTPUT_DIR}")

        setup_env()

        # Add ComfyUI to path to ensure modules are findable
        if COMFY_PATH not in sys.path: sys.path.insert(0, COMFY_PATH)
        
        # Start ComfyUI if not running
        if not check_comfy_status():
            log("Launching ComfyUI...")
            subprocess.Popen([sys.executable, os.path.join(COMFY_PATH, "main.py"), "--listen", "0.0.0.0", "--port", "8188"])
            # Wait for ComfyUI to start (up to 10 minutes for cold start)
            for _ in range(600): # 600 * 1s = 10 mins
                if check_comfy_status():
                    log("ComfyUI is ready!")
                    break
                time.sleep(1)
            else:
                log("ComfyUI failed to start in time")
                sys.exit(1)

        # Download Models
        active_loras = ensure_models(custom_loras=job_input.get("loras", []))

        # Build Workflow
        workflow = build_workflow(
            prompt_text=job_input.get("prompt", ""),
            negative_prompt=job_input.get("negative_prompt", ""),
            width=job_input.get("width", 1024),
            height=job_input.get("height", 1024),
            seed=job_input.get("seed", random.randint(1, int(1e15))),
            steps=job_input.get("steps", 35),
            cfg=job_input.get("cfg", 5.0),
            sampler_name=job_input.get("sampler_name", "dpmpp_2m"),
            scheduler=job_input.get("scheduler", "karras"),
            controlnet_image=job_input.get("controlnet_image"), # Renamed from face_image
            face_swap_image=job_input.get("face_swap_image"), # New field
            identity_strength=job_input.get("identity_strength", 0.6),
            loras=active_loras,
            job_id=job_id
        )

        # Queue Prompt
        start_time = time.time()
        response = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow, "client_id": job_id})
        if response.status_code != 200:
            return {"error": f"ComfyUI Error: {response.text}"}

        # Wait for Result
        deadline = time.time() + 600
        while time.time() < deadline:
            img = get_latest_image(job_id, min_timestamp=start_time)
            if img:
                log(f"Found image for {job_id}. Size: {len(img)} chars")
                return {"status": "success", "image_base64": img}
            
            # Debug: List files
            files = os.listdir(OUTPUT_DIR)
            log(f"Waiting for {job_id}_*.png. Files in output: {len(files)}")
            if len(files) > 0:
                log(f"Sample files: {files[:3]}")
                
            time.sleep(2)

        log("Timeout waiting for image")
        return {"error": "Generation timeout"}

    except Exception as e:
        import traceback
        return {"error": f"{str(e)}\n{traceback.format_exc()}"}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
