# Switch to official PyTorch 2.4.0 image to support new ComfyUI requirements
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Install system dependencies (build-essential added)
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

# --- INSIGHTFACE & DEEPFAKE PRE-REQUISITES ---
# 1. Upgrade pip and install build tools
RUN pip install --upgrade pip setuptools wheel

# 2. Install numpy and cython FIRST (Required for building insightface)
RUN pip install "numpy<2.0.0" cython

# 3. Install onnxruntime-gpu compatible with CUDA 12
RUN pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/

# 4. Install InsightFace
RUN pip install insightface
# ---------------------------------------------

# Install Python dependencies
COPY requirements.txt .
# No need to reinstall torch, it's in the base image. Just install requirements.
RUN pip install -r requirements.txt && \
    pip install "numpy<2.0.0"

# Install ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# SMART INSTALL: Remove heavy deps (torch, numpy) from ComfyUI requirements 
# to use our pre-installed versions, but install everything else (alembic, etc).
RUN sed -i '/torch/d' /app/ComfyUI/requirements.txt && \
    sed -i '/numpy/d' /app/ComfyUI/requirements.txt && \
    sed -i '/Pillow/d' /app/ComfyUI/requirements.txt && \
    pip install -r /app/ComfyUI/requirements.txt

# Copy project files
COPY . /app

# Expose ports
EXPOSE 8188

# Set entrypoint
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
