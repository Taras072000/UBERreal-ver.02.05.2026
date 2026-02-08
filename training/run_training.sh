#!/bin/bash
set -e

# Configuration
DATASET_DIR="/app/training/dataset"
OUTPUT_DIR="/app/training/output"
MODEL_NAME="PonyRealism_v2.1"
LORA_NAME="UBERreal_Anatomy_v1"

echo "=== UBERreal Training Pipeline ==="
echo "Step 1: Preparing Environment..."

# Install Training Dependencies
pip install -r /app/training/requirements_train.txt

# Clone Kohya SD-Scripts if not exists
if [ ! -d "/app/training/sd-scripts" ]; then
    git clone https://github.com/kohya-ss/sd-scripts.git /app/training/sd-scripts
fi

cd /app/training/sd-scripts

echo "Step 2: Auto-Tagging Images..."
# Run the tagger script
python3 /app/training/scripts/tag_images.py --dir "$DATASET_DIR" --thresh 0.35

echo "Step 3: Starting LoRA Training..."
# Accelerate launch command for SDXL LoRA
accelerate launch --num_cpu_threads_per_process=2 sdxl_train_network.py \
    --pretrained_model_name_or_path="/app/ComfyUI/models/checkpoints/PonyRealism_v2.1.safetensors" \
    --train_data_dir="$DATASET_DIR" \
    --output_dir="$OUTPUT_DIR" \
    --output_name="$LORA_NAME" \
    --network_module="networks.lora" \
    --network_dim=32 \
    --network_alpha=16 \
    --resolution="1024,1024" \
    --train_batch_size=1 \
    --max_train_epochs=10 \
    --save_every_n_epochs=1 \
    --mixed_precision="fp16" \
    --save_precision="fp16" \
    --optimizer_type="Adafactor" \
    --learning_rate=1e-4 \
    --text_encoder_lr=5e-5 \
    --unet_lr=1e-4 \
    --no_metadata \
    --gradient_checkpointing \
    --xformers \
    --cache_latents

echo "=== Training Complete! ==="
echo "LoRA saved to $OUTPUT_DIR/$LORA_NAME.safetensors"
