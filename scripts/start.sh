#!/bin/bash
set -e

echo "=== UBERreal System Startup ==="

# Check if /workspace is mounted (RunPod Persistent Volume)
if [ -d "/workspace" ]; then
    echo "Persistent Volume detected at /workspace"
    
    # Create directory structure in Persistent Volume if not exists
    mkdir -p /workspace/models/checkpoints
    mkdir -p /workspace/models/loras
    mkdir -p /workspace/models/controlnet
    mkdir -p /workspace/models/upscale_models
    mkdir -p /workspace/output
    mkdir -p /workspace/datasets
    
    # Symlink ComfyUI output to Persistent Volume
    rm -rf /app/ComfyUI/output
    ln -s /workspace/output /app/ComfyUI/output
    
    # Symlink Models (This allows adding models to PV and having ComfyUI see them)
    # Note: We might need a more sophisticated linking strategy if we want to mix baked-in models and PV models
    # For now, let's link the whole models directory if it's empty in the container, or just specific subfolders
    
    # Strategy: Link specific folders
    rm -rf /app/ComfyUI/models/checkpoints
    ln -s /workspace/models/checkpoints /app/ComfyUI/models/checkpoints
    
    rm -rf /app/ComfyUI/models/loras
    ln -s /workspace/models/loras /app/ComfyUI/models/loras
    
    rm -rf /app/ComfyUI/models/controlnet
    ln -s /workspace/models/controlnet /app/ComfyUI/models/controlnet
    
else
    echo "WARNING: No Persistent Volume found. Using container storage (ephemeral)."
fi

# Run Provisioning (Model Download)
if [ -f "scripts/provision.sh" ]; then
    echo "Running provision script..."
    chmod +x scripts/provision.sh
    ./scripts/provision.sh
fi

# Start ComfyUI in background
echo "Starting ComfyUI..."
cd /app/ComfyUI
# --listen 0.0.0.0 allows external access (useful for debugging via RunPod proxy)
python main.py --listen 0.0.0.0 --port 8188 --preview-method auto &
COMFY_PID=$!

echo "ComfyUI started with PID $COMFY_PID"

# Start Telegram Bot
echo "Starting Telegram Bot..."
cd /app
# Check if .env exists, if not create from example or warn
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found. Bot might fail to start."
fi

# We use exec to let the bot take over the PID 1 if needed, or just run it.
# Since we have ComfyUI in background, we should probably run bot in foreground.
python -m bot.main

# If bot crashes, we might want to keep the container running for debugging
# wait $COMFY_PID
