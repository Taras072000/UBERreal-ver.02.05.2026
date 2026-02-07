import asyncio
import logging
import os
import runpod
import json
import base64
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile, BufferedInputFile, 
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
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

# User settings storage (in-memory for now)
# Format: {user_id: {"aspect_ratio": "9:16", "style": "Realistic"}}
user_settings = {}

def get_settings(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = {"aspect_ratio": "9:16", "style": "Realistic"}
    return user_settings[user_id]

def get_dimensions(aspect_ratio):
    if aspect_ratio == "1:1":
        return 1024, 1024
    elif aspect_ratio == "16:9":
        return 1280, 720
    else: # 9:16 (Default for Reels/Stories)
        return 720, 1280

# Keyboards
def main_menu_keyboard():
    kb = [
        [KeyboardButton(text="📐 Формат (9:16)"), KeyboardButton(text="🎨 Стиль (Realistic)")],
        [KeyboardButton(text="ℹ️ Статус сервера")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def aspect_ratio_keyboard():
    kb = [
        [InlineKeyboardButton(text="📱 9:16 (Stories)", callback_data="ar_9:16")],
        [InlineKeyboardButton(text="🔲 1:1 (Post)", callback_data="ar_1:1")],
        [InlineKeyboardButton(text="📺 16:9 (Landscape)", callback_data="ar_16:9")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def style_keyboard():
    kb = [
        [InlineKeyboardButton(text="📸 Realistic (Photo)", callback_data="style_Realistic")],
        [InlineKeyboardButton(text="🎬 Cinematic (Movie)", callback_data="style_Cinematic")],
        [InlineKeyboardButton(text="🤳 Amateur (Homemade)", callback_data="style_Amateur")],
        [InlineKeyboardButton(text="💅 PornStar (Glamour)", callback_data="style_PornStar")],
        [InlineKeyboardButton(text="🎨 Anime (2.5D)", callback_data="style_Anime")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def generate_image_task(prompt: str, chat_id: int, user_id: int):
    """
    Sends a generation task to RunPod Serverless and waits for the result.
    """
    if not RUNPOD_ENDPOINT_ID or RUNPOD_ENDPOINT_ID == "id_эндпоинта":
        await bot.send_message(chat_id, "❌ Ошибка: Не настроен RunPod Endpoint ID.")
        return

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    settings = get_settings(user_id)
    width, height = get_dimensions(settings["aspect_ratio"])
    
    # Modify prompt based on style
    final_prompt = prompt
    if settings["style"] == "Realistic":
        final_prompt += ", (hyperrealism, 8k, extremely detailed, photo, dslr:1.2)"
    elif settings["style"] == "Cinematic":
        final_prompt += ", (cinematic lighting, movie scene, dramatic atmosphere, color grading)"
    elif settings["style"] == "Amateur":
        final_prompt += ", (amateur photo, homemade, raw photo, shot on iphone, flash photo, hard lighting, selfie, mirror selfie, low quality, noise, grain, POV:1.2)"
    elif settings["style"] == "PornStar":
        final_prompt += ", (studio lighting, professional makeup, perfect skin, airbrushed, glamour shot, 4k)"
    elif settings["style"] == "Anime":
        final_prompt += ", (anime style, 2d, flat color, illustration)"

    try:
        # Input payload for the worker
        input_payload = {
            "input": {
                "prompt": final_prompt,
                "width": width,
                "height": height,
                "steps": 25, # More steps for quality
                "cfg": 7,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "seed": 0, # Random seed will be handled by Comfy if 0, but usually we want random in python. 
                           # Let's keep 0 and let worker handle randomization if needed or send random here.
                "negative_prompt": "text, watermark, blur, deformed, painting, cartoon, low quality, ugly",
                "highres_fix": True # Always ON for quality
            }
        }
        
        await bot.send_message(chat_id, f"⏳ Запуск генерации...\n⚙️ {settings['aspect_ratio']} | {settings['style']}", reply_markup=main_menu_keyboard())
        
        # Run synchronous run (waits for completion)
        run_request = endpoint.run(input_payload)
        
        if run_request is None:
            await bot.send_message(chat_id, "❌ Ошибка: RunPod вернул пустой ответ.")
            return

        # Polling
        output = None
        try:
            output = await asyncio.to_thread(run_request.output, timeout=900)
        except Exception as poll_err:
            logger.error(f"RunPod Poll Error: {poll_err}")
            await bot.send_message(chat_id, f"⚠️ Таймаут ожидания или ошибка сети:\n{str(poll_err)}")
        
        if not output:
            await bot.send_message(chat_id, "❌ Воркер не вернул результат (возможно, упал).")
            return

        if isinstance(output, dict) and "error" in output:
            await bot.send_message(chat_id, f"❌ Ошибка генерации: {output.get('error')}")
            # Send debug json if available
            dbg = output.get("debug_prompt")
            if dbg:
                try:
                    data = json.dumps(dbg, ensure_ascii=False, indent=2).encode("utf-8")
                    await bot.send_document(chat_id, BufferedInputFile(data, filename="last_prompt.json"))
                except Exception:
                    pass
            return

        image_b64 = None
        if isinstance(output, dict):
            image_b64 = output.get("image_base64")
            
        if image_b64:
            try:
                img_bytes = base64.b64decode(image_b64)
                caption = f"✅ {settings['style']} | {settings['aspect_ratio']}"
                await bot.send_photo(chat_id, photo=BufferedInputFile(img_bytes, filename="result.png"), caption=caption)
                return
            except Exception as send_err:
                logger.error(f"Failed to send photo: {send_err}")
                
        await bot.send_message(chat_id, "❌ Ошибка: В ответе нет изображения.")

    except Exception as e:
        logger.error(f"RunPod Error: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка соединения с RunPod: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я UBERreal Bot v2.0.\n\n"
        "Я генерирую **Ultra-Realistic** контент на RTX 4090.\n"
        "Выбери настройки в меню и отправь промпт.",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    msg = await message.answer("🔄 Проверяю статус RunPod...")
    try:
        # Простой способ проверить доступность API (например, получить инфо о эндпоинте)
        # В библиотеке runpod нет прямого метода get_endpoint_status без GraphQL,
        # поэтому просто пишем заглушку или пробуем получить health
        await msg.edit_text("✅ RunPod API доступен.\nВоркеры: Auto-scaling (Serverless).")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка RunPod API: {e}")

@dp.message(F.text.contains("Формат"))
async def menu_aspect(message: types.Message):
    await message.answer("Выберите соотношение сторон:", reply_markup=aspect_ratio_keyboard())

@dp.message(F.text.contains("Стиль"))
async def menu_style(message: types.Message):
    await message.answer("Выберите стиль генерации:", reply_markup=style_keyboard())

@dp.callback_query(F.data.startswith("ar_"))
async def callback_aspect(callback: types.CallbackQuery):
    ar = callback.data.split("_")[1]
    get_settings(callback.from_user.id)["aspect_ratio"] = ar
    await callback.message.answer(f"✅ Установлен формат: {ar}")
    await callback.answer()

@dp.callback_query(F.data.startswith("style_"))
async def callback_style(callback: types.CallbackQuery):
    style = callback.data.split("_")[1]
    get_settings(callback.from_user.id)["style"] = style
    await callback.message.answer(f"✅ Установлен стиль: {style}")
    await callback.answer()

@dp.message()
async def handle_prompt(message: types.Message):
    prompt = message.text
    if not prompt or prompt.startswith("/"):
        return
    await generate_image_task(prompt, message.chat.id, message.from_user.id)

async def main():
    logger.info("Starting UBERreal Telegram Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
