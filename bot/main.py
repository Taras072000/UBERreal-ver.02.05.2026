import asyncio
import logging
import os
import runpod
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv

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
        # TODO: Add full workflow JSON here later
        input_payload = {
            "input": {
                "prompt": prompt,
                "workflow": {} # Placeholder for now
            }
        }
        
        await bot.send_message(chat_id, "⏳ Задача отправлена на сервер (Serverless)... Ожидайте.")
        
        # Run synchronous run (waits for completion)
        # Timeout is crucial here
        run_request = endpoint.run(input_payload)
        
        # Polling for status
        # Note: In production, use webhooks for better efficiency
        output = run_request.output(timeout=120) 
        
        if "error" in output:
             await bot.send_message(chat_id, f"❌ Ошибка генерации: {output['error']}")
        else:
            # Assuming output contains a URL or base64
            # For now, just echo success
            image_url = output.get("output") # Adjust based on actual worker response
            if image_url:
                 await bot.send_message(chat_id, f"✅ Готово! URL: {image_url}")
            else:
                 await bot.send_message(chat_id, "✅ Генерация завершена (нет URL в ответе).")

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
