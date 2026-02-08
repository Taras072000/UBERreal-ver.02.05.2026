#!/bin/bash
# Universal Fix & Run script for RunPod GPU Pod

# 1. Export library paths for CUDA/cuDNN
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/python3.10/dist-packages/nvidia/cudnn/lib

# 2. Update/Install necessary dependencies
pip install --upgrade pip
pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/
pip install -r training/requirements_train.txt

# 3. Fix paths in the main training script to match Pod structure
# Replacing /app/ with /workspace/UBERreal-ver.02.05.2026/
sed -i 's|/app/|/workspace/UBERreal-ver.02.05.2026/|g' training/run_training.sh

# 4. Remove --xformers if it causes issues (using SDPA instead)
sed -i 's/--xformers//g' training/run_training.sh

# 5. Make sure the script is executable and run it
chmod +x training/run_training.sh
bash training/run_training.sh
