# RunPod Deployment Guide for UBERreal

## 1. Подготовка
1.  Зарегистрируйтесь на [RunPod.io](https://runpod.io).
2.  Пополните баланс ($10-20 достаточно для старта).

## 2. Выбор GPU
Для разработки и тестов рекомендую:
*   **GPU**: RTX 4090 (24GB VRAM) — лучшее соотношение цена/качество.
*   **Тип**: Community Cloud (дешевле) или Secure Cloud (стабильнее).

## 3. Настройка Pod (Template)
При создании пода выберите:
*   **Template**: `RunPod PyTorch 2.1` (или аналогичный с CUDA 11.8/12.1).
*   **Container Image**: `pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime` (или используйте наш Dockerfile, если умеете собирать).
*   **Container Disk**: 20 GB.
*   **Volume Disk**: 50 GB (минимум, сюда будем качать модели).
*   **Volume Mount Path**: `/workspace` (ОБЯЗАТЕЛЬНО).

## 4. Environment Variables
Добавьте переменные окружения:
*   `BOT_TOKEN`: Ваш токен от Telegram бота (получите у @BotFather).

## 5. Запуск
После старта пода:
1.  Подключитесь через Web Terminal или Jupyter Lab.
2.  Клонируйте этот репозиторий (или загрузите файлы).
3.  Запустите скрипт установки:
    ```bash
    chmod +x scripts/start.sh
    ./scripts/start.sh
    ```

## 6. Проверка
*   **ComfyUI**: Будет доступен на порту `8188` (используйте кнопку "Connect" -> "8188" в интерфейсе RunPod).
*   **Bot**: Должен ответить в Telegram.

## Примечание
Для продакшена мы соберем свой Docker Image, чтобы не устанавливать зависимости каждый раз.
