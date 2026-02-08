# Use PyTorch 2.4.0 to support ComfyUI's new torch.uint64 requirement
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    unzip \
    build-essential \
    python3-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# --- PRE-INSTALL HEAVY DEPENDENCIES ---
# Force numpy < 2.0.0 globally to avoid torch/numpy 2.0 compatibility issues
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir "numpy<2.0.0" cython && \
    pip install --no-cache-dir onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/ && \
    pip install --no-cache-dir insightface

# Install ComfyUI (Pinned to ensure compatibility with PyTorch 2.4)
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI && \
    pip install --no-cache-dir -r /app/ComfyUI/requirements.txt

# Install Project requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "numpy<2.0.0"

# Copy project files
COPY . /app

# Expose ports
EXPOSE 8188

# Set entrypoint
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
