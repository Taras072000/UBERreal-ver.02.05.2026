#!/bin/bash
set -e

# Get the project root directory (directory where this script is located + up one level)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Configuration
DATASET_DIR="$PROJECT_ROOT/training/dataset"
OUTPUT_DIR="$PROJECT_ROOT/training/output"
MODEL_NAME="PonyRealism_v2.1"
LORA_NAME="UBERreal_Anatomy_v1"

echo "=== UBERreal Training Pipeline ==="
echo "Project Root: $PROJECT_ROOT"
echo "Step 1: Preparing Environment..."

# Install Training Dependencies
pip install -r "$PROJECT_ROOT/training/requirements_train.txt"

# Clone Kohya SD-Scripts if not exists
if [ ! -d "$PROJECT_ROOT/training/sd-scripts" ]; then
    echo "Cloning Kohya sd-scripts..."
    git clone https://github.com/kohya-ss/sd-scripts.git "$PROJECT_ROOT/training/sd-scripts"
fi

cd "$PROJECT_ROOT/training/sd-scripts"

echo "Step 2: Auto-Tagging Images..."
# Run the tagger script
python3 "$PROJECT_ROOT/training/scripts/tag_images.py" --dir "$DATASET_DIR" --thresh 0.35

echo "Step 3: Starting LoRA Training..."
# Accelerate launch command for SDXL LoRA
# Note: Adjusted pretrained_model_name_or_path to look in common RunPod locations if ComfyUI isn't in project root
CHECKPOINT_PATH="$PROJECT_ROOT/ComfyUI/models/checkpoints/PonyRealism_v2.1.safetensors"

if [ ! -f "$CHECKPOINT_PATH" ]; then
    # Fallback to standard RunPod path if not found in project
    CHECKPOINT_PATH="/workspace/ComfyUI/models/checkpoints/PonyRealism_v2.1.safetensors"
fi

if [ ! -f "$CHECKPOINT_PATH" ]; then
    echo "ERROR: Base model not found at $CHECKPOINT_PATH"
    echo "Please ensure PonyRealism_v2.1.safetensors is in ComfyUI/models/checkpoints/"
    exit 1
fi

accelerate launch --num_cpu_threads_per_process=2 sdxl_train_network.py \
    --pretrained_model_name_or_path="$CHECKPOINT_PATH" \
    --train_data_dir="$DATASET_DIR" \
    --output_dir="$OUTPUT_DIR" \
    --output_name="$LORA_NAME" \
    --network_module="networks.lora" \
    --network_dim=32 \
    --network_alpha=16 \
    --resolution="1024,1024" \
    --caption_extension=".txt" \
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
