# Use RunPod's official PyTorch image (includes Torch, CUDA, cuDNN)
# This prevents downloading 2GB+ of torch wheels at runtime and fixes "No space left on device"
FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel

# Install system dependencies (libgl1 for opencv)
RUN apt-get update && apt-get install -y \
    git wget curl procps build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install basic python tools
RUN pip install --no-cache-dir runpod requests

WORKDIR /app

# Copy repository
COPY . /app

# Start handler
CMD ["python", "-u", "engine/serverless_handler.py"]
