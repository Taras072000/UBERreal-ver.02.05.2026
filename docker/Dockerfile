FROM python:3.11-slim

# Минимальные системные зависимости
RUN apt-get update && apt-get install -y \
    git wget curl procps build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Ставим только базовый runpod и requests
RUN pip install --no-cache-dir runpod requests

WORKDIR /app

# ВАЖНО: Мы не используем COPY . /app, чтобы избежать ошибки "disk quota exceeded" при сборке.
# Вместо этого воркер скачает актуальный код из GitHub прямо при запуске.
CMD ["/bin/bash", "-c", "git clone https://github.com/Taras072000/UBERreal-ver.02.05.2026.git . && python -u engine/serverless_handler.py"]
