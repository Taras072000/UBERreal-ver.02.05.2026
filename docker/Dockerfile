# Используем официальный образ как фундамент
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Ставим только системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка библиотек в образ (как и раньше)
RUN pip install --upgrade pip && \
    pip install runpod requests transformers==4.38.2 imagesize onnxruntime-gpu insightface

# Копируем код проекта
COPY . /app

# ComfyUI теперь будет жить на твоем Network Volume (диск 50ГБ)
# Это спасет билд от переполнения, а воркер будет работать быстрее
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
