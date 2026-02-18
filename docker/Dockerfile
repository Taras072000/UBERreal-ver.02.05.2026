FROM python:3.11-slim

# Минимальные системные зависимости
RUN apt-get update && apt-get install -y \
    git wget curl procps build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Ставим только базовый runpod и requests
RUN pip install --no-cache-dir runpod requests

WORKDIR /app

# Копируем всё содержимое репозитория в контейнер
COPY . /app

# Запускаем хендлер
CMD ["python", "-u", "engine/serverless_handler.py"]
