FROM python:3.11-slim

# Минимальные системные зависимости для сборки некоторых библиотек
RUN apt-get update && apt-get install -y \
    git wget curl procps build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Ставим только базовый runpod и requests
RUN pip install --no-cache-dir runpod requests

WORKDIR /app
COPY . /app

# Запускаем обработчик, который сам доставит всё нужное на диск
CMD ["python", "-u", "/app/engine/serverless_handler.py"]
