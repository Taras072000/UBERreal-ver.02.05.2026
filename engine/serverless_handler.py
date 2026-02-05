import runpod
import os
import json
import base64
import time
import requests
from io import BytesIO

# URL локального ComfyUI (внутри контейнера Serverless)
COMFY_URL = "http://127.0.0.1:8188"

def check_comfy_status():
    """Ожидание готовности ComfyUI"""
    for _ in range(30):
        try:
            response = requests.get(f"{COMFY_URL}/system_stats")
            if response.status_code == 200:
                return True
        except:
            time.sleep(1)
    return False

def handler(job):
    """
    Основная функция-обработчик RunPod Serverless.
    """
    job_input = job["input"]
    prompt_text = job_input.get("prompt", "")
    workflow = job_input.get("workflow", {}) # Полный JSON workflow

    # 1. Проверка ComfyUI
    if not check_comfy_status():
        return {"error": "ComfyUI failed to start within timeout"}

    # 2. Если workflow пустой, берем дефолтный
    if not workflow:
        try:
            with open("/app/engine/workflows/default_text2img.json", "r") as f:
                workflow = json.load(f)
        except Exception as e:
            return {"error": f"Failed to load default workflow: {str(e)}"}

    # 3. Инъекция промпта в Workflow
    # Ищем ноду CLIPTextEncode (обычно id 6 или 7 в нашем json)
    # Это упрощенная логика, в идеале нужно искать по type="CLIPTextEncode"
    if prompt_text:
        for node in workflow.get("nodes", []):
            if node.get("type") == "CLIPTextEncode" and node.get("widgets_values"):
                # Эвристика: если текущий текст не "negative", заменяем его
                current_text = node["widgets_values"][0]
                if isinstance(current_text, str) and "text" not in current_text and "blur" not in current_text:
                     node["widgets_values"][0] = prompt_text
                     break

    # 4. Отправка задачи в ComfyUI API (/prompt)
    try:
        p = {"prompt": workflow}
        response = requests.post(f"{COMFY_URL}/prompt", json=p)
        prompt_id = response.json().get("prompt_id")
    except Exception as e:
        return {"error": f"Failed to queue prompt: {str(e)}"}

    # 5. Ожидание результата (Polling history)
    # В Serverless мы должны дождаться завершения и вернуть картинку
    # ComfyUI сохраняет картинки в output/
    
    # Упрощенная логика ожидания (нужно доработать через WebSocket для скорости)
    time.sleep(10) # Placeholder wait
    
    # 6. Получение последней картинки
    # ... logic to find latest image in output dir ...
    
    return {"status": "success", "output": "http://placeholder-url.com/image.png"}

# Запуск ComfyUI в фоне (если еще не запущен)
# Используем nohup или subprocess.Popen
if not check_comfy_status():
    # Важно: путь к main.py должен быть верным внутри Docker контейнера
    import subprocess
    subprocess.Popen(["python3", "/app/ComfyUI/main.py", "--listen", "0.0.0.0", "--port", "8188"])

runpod.serverless.start({"handler": handler})
