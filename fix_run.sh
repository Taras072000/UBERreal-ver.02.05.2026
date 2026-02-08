#!/bin/bash
# Universal Fix & Run script for RunPod GPU Pod

# 1. Export library paths for CUDA/cuDNN
# Try multiple common paths for RunPod and official images
CUDNN_PATH=$(find /usr/local -name libcudnn.so.9 | head -n 1)
if [ -n "$CUDNN_PATH" ]; then
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(dirname $CUDNN_PATH)
fi

# 2. Update/Install necessary dependencies
pip install --upgrade pip
pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/
pip install -r training/requirements_train.txt
pip install transformers==4.38.2  # Critical fix for CLIPFeatureExtractor error

# 3. Fix paths in the main training script to match Pod structure
# Replacing /app/ with /workspace/UBERreal-ver.02.05.2026/
sed -i 's|/app/|/workspace/UBERreal-ver.02.05.2026/|g' training/run_training.sh

# 4. Remove --xformers if it causes issues (using SDPA instead)
sed -i 's/--xformers//g' training/run_training.sh

# 5. Make sure the script is executable and run it
chmod +x training/run_training.sh
bash training/run_training.sh
