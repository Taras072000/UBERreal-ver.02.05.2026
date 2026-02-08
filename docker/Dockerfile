# Ultra-lightweight Dockerfile
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install only basic system tools (libgl1 instead of libgl1-mesa-glx for Debian Trixie compatibility)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 build-essential python3-venv \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only runpod and basic requests
RUN pip install --upgrade pip && \
    pip install runpod requests

# Copy project code
COPY . /app

# The handler will install everything else onto the Network Volume
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
