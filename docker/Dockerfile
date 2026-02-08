# Use PyTorch 2.4.0 (Standard image, not devel, to save space)
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Basic tools only
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg libsm6 libxext6 libgl1-mesa-glx libglib2.0-0 build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-install core ML libraries (one layer)
RUN pip install --upgrade pip setuptools wheel && \
    pip install "numpy<2.0.0" insightface onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/

# Install ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI && \
    pip install -r /app/ComfyUI/requirements.txt

# Project requirements
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install "numpy<2.0.0"

# Copy handler
COPY . /app

CMD ["python", "-u", "/app/engine/serverless_handler.py"]
