# Base image with CUDA 12.1 and PyTorch 2.1.2 (Using runtime to force cache refresh)
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

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
    unzip \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install InsightFace & ONNX Runtime (using script)
COPY scripts/install_insightface.sh /app/scripts/
RUN bash /app/scripts/install_insightface.sh

# Install ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI
RUN cd /app/ComfyUI && pip install -r requirements.txt

# Install ComfyUI Manager
RUN cd /app/ComfyUI/custom_nodes && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# Install ReActor Node (Deepfake)
RUN cd /app/ComfyUI/custom_nodes && \
    git clone https://github.com/Gourieff/comfyui-reactor-node.git && \
    cd comfyui-reactor-node && \
    pip install -r requirements.txt

# Copy project files
COPY . /app

# Expose ports
EXPOSE 8188

# Set entrypoint
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
