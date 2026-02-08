# Base image with CUDA 12.1 and PyTorch 2.2 (RunPod official image for faster caching)
FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

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

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121 && \
    pip install -r requirements.txt

# Install ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI
RUN cd /app/ComfyUI && pip install -r requirements.txt

# Install ComfyUI Custom Nodes (Impact Pack for Face Detailer)
RUN cd /app/ComfyUI/custom_nodes && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    cd ComfyUI-Impact-Pack && \
    pip install -r requirements.txt && \
    python install.py

# Copy project files
COPY . /app

# Expose ports
EXPOSE 8188

# Set entrypoint
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
