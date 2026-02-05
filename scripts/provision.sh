#!/bin/bash
# Provision script to download essential models if they don't exist

echo "=== Provisioning Models ==="

MODELS_PATH="/app/ComfyUI/models"
# If symlinked, this points to /workspace/models...

# Function to download file if not exists
download_if_missing() {
    local url="$1"
    local dest="$2"
    
    if [ ! -f "$dest" ]; then
        echo "Downloading $(basename "$dest")..."
        wget -q --show-progress "$url" -O "$dest"
    else
        echo "$(basename "$dest") already exists."
    fi
}

# 1. Download SDXL Checkpoint (Juggernaut XL or RealVisXL)
# Using Juggernaut XL v9 as a safe bet for realism
JUGGERNAUT_URL="https://civitai.com/api/download/models/357609" # Juggernaut XL V9
download_if_missing "$JUGGERNAUT_URL" "$MODELS_PATH/checkpoints/juggernautXL_v9.safetensors"

# 2. Download ControlNet Models (OpenPose, Depth) for SDXL
# These are large, so only download if essential
# diffusers/controlnet-canny-sdxl-1.0 is hosted on HF
# We need ComfyUI compatible .safetensors

# OpenPose XL
# https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors
download_if_missing "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors" "$MODELS_PATH/controlnet/OpenPoseXL2.safetensors"

# Depth XL
# https://huggingface.co/diffusers/controlnet-depth-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors (Needs conversion or specific file)
# Better use: https://huggingface.co/xinsir/controlnet-depth-sdxl-1.0
# download_if_missing "..." "..."

echo "Provisioning complete."
