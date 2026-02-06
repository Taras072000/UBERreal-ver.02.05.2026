import asyncio
import logging
import os
import runpod
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Bot and Dispatcher
BOT_TOKEN = os.getenv("BOT_TOKEN")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is missing!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# RunPod Configuration
runpod.api_key = RUNPOD_API_KEY

def load_workflow_with_prompt(prompt: str) -> dict:
    """Загружает дефолтный workflow и подставляет положительный промпт"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        wf_path = os.path.normpath(os.path.join(base_dir, "..", "engine", "workflows", "default_text2img.json"))
        with open(wf_path, "r") as f:
            workflow = json.load(f)
        if prompt:
            for node in workflow.get("nodes", []):
                if node.get("type") == "CLIPTextEncode" and node.get("widgets_values"):
                    node["widgets_values"][0] = prompt
                    break
        return workflow
    except Exception as e:
        logger.error(f"Failed to load workflow: {e}")
        return {}

async def generate_image_task(prompt: str, chat_id: int):
    """
    Sends a generation task to RunPod Serverless and waits for the result.
    """
    if not RUNPOD_ENDPOINT_ID or RUNPOD_ENDPOINT_ID == "id_эндпоинта":
        await bot.send_message(chat_id, "❌ Ошибка: Не настроен RunPod Endpoint ID.")
        return

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    
    try:
        # Input payload for the worker
        input_payload = {
            "input": {
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "steps": 20,
                "cfg": 8,
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": 0,
                "negative_prompt": "text, watermark, blur, deformed, painting, cartoon"
            }
        }
        
        await bot.send_message(chat_id, "⏳ Задача отправлена на сервер (Serverless)... Ожидайте.")
        
        # Run synchronous run (waits for completion)
        # Timeout is crucial here
        run_request = endpoint.run(input_payload)
        
        # Polling for status
        # Note: In production, use webhooks for better efficiency
        if run_request is None:
            await bot.send_message(chat_id, "❌ Ошибка: RunPod вернул пустой ответ на запуск задачи.")
            return
        await bot.send_message(chat_id, "🕓 Задача принята. Это может занять 2–6 минут.")
        # Выполняем блокирующий опрос в отдельном потоке, чтобы не блокировать Telegram-поллинг
        output = None
        try:
            # run_request.output(timeout=...) блокирует поток до завершения или таймаута
            output = await asyncio.to_thread(run_request.output, timeout=600)
        except Exception as poll_err:
            logger.error(f"RunPod Poll Error: {poll_err}")
            await bot.send_message(chat_id, f"⚠️ Debug: Ошибка при ожидании ответа от RunPod:\n{str(poll_err)}")
        
        if not output:
            await bot.send_message(chat_id, "❌ Ошибка: пустой ответ от RunPod (None). Возможно, воркер упал.")
            return
        if isinstance(output, dict) and "error" in output:
            await bot.send_message(chat_id, f"❌ Ошибка генерации: {output.get('error')}")
            dbg = output.get("debug_prompt")
            if dbg:
                try:
                    import json
                    from aiogram.types import BufferedInputFile
                    data = json.dumps(dbg, ensure_ascii=False, indent=2).encode("utf-8")
                    await bot.send_document(chat_id, BufferedInputFile(data, filename="last_prompt.json"))
                except Exception as send_err:
                    logger.error(f"Failed to send debug prompt: {send_err}")
            return
        image_b64 = None
        if isinstance(output, dict):
            image_b64 = output.get("image_base64")
        if image_b64:
            try:
                import base64
                img_bytes = base64.b64decode(image_b64)
                from aiogram.types import BufferedInputFile
                await bot.send_photo(chat_id, photo=BufferedInputFile(img_bytes, filename="result.png"), caption="✅ Готово")
                return
            except Exception as send_err:
                logger.error(f"Failed to send photo: {send_err}")
        await bot.send_message(chat_id, "❌ Ошибка: В ответе нет изображения. Попробуй еще раз.")

    except Exception as e:
        logger.error(f"RunPod Error: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка соединения с RunPod: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я UBERreal Bot.\n\n"
                         "Я работаю на RunPod Serverless (оплата только за генерацию).\n"
                         "Отправь мне промпт, чтобы начать (пока тестовый режим).")

@dp.message()
async def handle_prompt(message: types.Message):
    prompt = message.text
    if not prompt:
        return
    
    await generate_image_task(prompt, message.chat.id)

async def main():
    logger.info("Starting UBERreal Telegram Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
