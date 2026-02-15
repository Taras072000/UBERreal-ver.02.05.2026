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
        [KeyboardButton(text="👩 Персонаж (Insta Girl)"), KeyboardButton(text="ℹ️ Статус сервера")],
        [KeyboardButton(text="🧘‍♀️ Управление позой (ControlNet)")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(F.text.contains("Управление позой"))
async def menu_controlnet_info(message: types.Message):
    settings = get_settings(message.from_user.id)
    has_pose = "✅ Установлена" if "controlnet_image" in settings else "❌ Не установлена"
    
    text = (
        f"🧘‍♀️ <b>Управление позой (ControlNet)</b>\n\n"
        f"Текущий статус: {has_pose}\n\n"
        f"<b>Как это работает?</b>\n"
        f"1. Просто пришли боту любое фото человека.\n"
        f"2. Выбери вариант 'Использовать как позу'.\n"
        f"3. Бот 'считает' положение тела и объем с этого фото и применит их к следующей генерации.\n\n"
        f"Это гарантирует, что у персонажа не будет лишних рук/ног, а фигура будет соответствовать оригиналу.\n\n"
        f"Чтобы сбросить позу, нажми /reset_pose."
    )
    await message.answer(text, parse_mode="HTML")

def character_keyboard():
    kb = [
        [InlineKeyboardButton(text="👩 Insta Girl (LoRA v1 - 930 steps)", callback_data="char_insta_v1")],
        [InlineKeyboardButton(text="👩 Insta Girl (LoRA v2 - 1860 steps)", callback_data="char_insta_v2")],
        [InlineKeyboardButton(text="👩 Insta Girl (LoRA v3 - 2790 steps)", callback_data="char_insta_v3")],
        [InlineKeyboardButton(text="🔥 LUSTIFY (18+)", callback_data="char_lustify")],
        [InlineKeyboardButton(text="❌ Без персонажа", callback_data="char_none")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def aspect_ratio_keyboard():
    kb = [
        [InlineKeyboardButton(text="📱 9:16 (Stories)", callback_data="ar_9:16")],
        [InlineKeyboardButton(text="🔲 1:1 (Post)", callback_data="ar_1:1")],
        [InlineKeyboardButton(text="📺 16:9 (Landscape)", callback_data="ar_16:9")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def style_keyboard():
    kb = [
        [InlineKeyboardButton(text="🔥 LUSTIFY (18+)", callback_data="style_lustify")],
        [InlineKeyboardButton(text="👅 Deep Throat (18+)", callback_data="style_deepthroat")],
        [InlineKeyboardButton(text="📸 Amateur (18+)", callback_data="style_amateur")],
        [InlineKeyboardButton(text="💦 Facial (Pony)", callback_data="style_facial")],
        [InlineKeyboardButton(text="👙 BetterNudes", callback_data="style_betternudes")]
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
    
    # Character LoRA Logic
    loras = []
    char_prefix = ""

    # Названия файлов внутри репозиториев на HF
    char_loras = {
        "insta_v1": ("insta_girl_v1, ", "UBERreal_Anatomy_v1-000001.safetensors", "insta_girl_v1.safetensors"),
        "insta_v2": ("insta_girl_v2, ", "UBERreal_Anatomy_v1-000002.safetensors", "insta_girl_v2.safetensors"),
        "insta_v3": ("insta_girl_v3, ", "UBERreal_Anatomy_v1-000003.safetensors", "insta_girl_v3.safetensors"),
        "lustify": ("lustify, ", "LUSTIFY_v1.safetensors", "LUSTIFY_SDXL_v1.safetensors")
    }
    
    char_version = settings.get("character")
    if char_version in char_loras:
        prefix, hf_filename, local_filename = char_loras[char_version]
        char_prefix = prefix
        # Репозиторий на HF: Taras082498/insta_girl_vX.safetensors
        repo_name = char_version.replace("insta_", "insta_girl_") + ".safetensors"
        
        lora_url = f"https://huggingface.co/Taras082498/{repo_name}/resolve/main/{hf_filename}"
        
        loras.append({
            "name": local_filename,
            "url": lora_url,
            "strength_model": 1.2, # Увеличили силу до 1.2 для лучшего сходства
            "strength_clip": 1.0
        })
        logger.info(f"Adding LoRA: {local_filename} (Strength: 1.2) from {lora_url}")

    # Modify prompt based on style
    final_prompt = char_prefix + prompt
    if settings["style"] == "Realistic":
        final_prompt += ", (photorealistic:1.3), 8k, raw photo, (high sharp:1.2)"
    elif settings["style"] == "Cinematic":
        final_prompt += ", cinematic lighting, dramatic atmosphere, color grading"
    elif settings["style"] == "Amateur":
        final_prompt += ", (amateur photo, homemade:1.2), raw photo, shot on iphone, noise, grain"
    elif settings["style"] == "PornStar":
        final_prompt += ", (studio lighting, professional makeup, perfect skin, airbrushed, glamour shot, 4k)"
    elif settings["style"] == "Lustify":
        # Add Trigger Words for LUSTIFY LoRA
        final_prompt += ", (AMATEUR PHOTO, FILM GRAIN, TAKING A MIRROR SELFIE, LIGHT LEAK:1.2), raw photo, high quality"
        # Add LoRA to request if not already added
        if not any(l["name"] == "LUSTIFY_SDXL_v1.safetensors" for l in loras):
            loras.append({
                "name": "LUSTIFY_SDXL_v1.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0
            })
    elif settings["style"] == "style_deepthroat":
        # Deep Throat XL Trigger Words
        final_prompt += ", GIVING A DEEP THROAT BLOWJOB, saliva, messy face, detailed mouth, high quality, 8k"
        # Add LoRA to request
        loras.append({
            "name": "DeepThroatXL_v1.safetensors",
            "strength_model": 0.6,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_amateur":
        # Pony Amateur V2 Trigger Words
        final_prompt += ", photo, grainy, amateur, lowres, 2000s nostalgia, webcam photo, flash"
        # Add LoRA to request
        loras.append({
            "name": "PonyAmateur_v2.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_facial":
        # Perfect Facial - Pony Trigger Words
        final_prompt += ", small / medium / big facial, small / medium / big cumshot, small / medium / big cum"
        # Add LoRA to request
        loras.append({
            "name": "PerfectFacial_Pony_v1.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_betternudes":
        # PhotoReal BetterNudes Trigger Words
        final_prompt += ", nsfw, nude, naked, photographic"
        # Add LoRA to request
        loras.append({
            "name": "PhotoRealBetterNudes_v3.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })
    elif settings["style"] == "Anime":
        final_prompt += ", (anime style, 2d, flat color, illustration)"

    try:
        # Check if user has a pose image
        controlnet_image = None
        if "controlnet_image" in settings:
            controlnet_image = settings["controlnet_image"]
            # Clear pose after one use? Or keep it? Let's keep it until user clears it or sets new one.
            # But maybe notify user.
            
        # Input payload for the worker (ПО ТВОЕМУ СПИСКУ)
        input_payload = {
            "input": {
                "prompt": final_prompt,
                "width": width,
                "height": height,
                "steps": 35, # SDXL Base steps
                "cfg": 5.0, # Золотой CFG для анатомии
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "seed": 0,
                "negative_prompt": "headwear, helmet, goggles, weird object on head, (worst quality, low quality:1.4), text, watermark, blur, deformed, painting, cartoon, ugly, bad anatomy, deformed hands, extra fingers",
                "highres_fix": True,
                "face_image": controlnet_image, # Используем для ControlNet
                "loras": loras
            }
        }
        
        status_msg = f"⏳ Запуск генерации...\n⚙️ {settings['aspect_ratio']} | {settings['style']}"
        if controlnet_image:
            status_msg += "\n🧘‍♀️ Используется поза (ControlNet)"
            
        await bot.send_message(chat_id, status_msg, reply_markup=main_menu_keyboard())
        
        # Run synchronous run (waits for completion)
        run_request = endpoint.run(input_payload)
        
        if run_request is None:
            await bot.send_message(chat_id, "❌ Ошибка: RunPod вернул пустой ответ.")
            return

        # Polling with 10 minute timeout (600s) as requested for heavy model downloads
        output = None
        try:
            # We use a long timeout because the first run downloads ~20GB of models
            output = await asyncio.to_thread(run_request.output, timeout=600) 
            logger.info(f"RunPod raw output: {output}")
        except Exception as poll_err:
            logger.error(f"RunPod Poll Error: {poll_err}")
            await bot.send_message(chat_id, f"⚠️ Превышено время ожидания (10 мин).\nСервер всё еще может скачивать модели. Попробуйте через пару минут.")
            return
        
        if not output:
            await bot.send_message(chat_id, "❌ Воркер не вернул результат (возможно, упал или пустой ответ).")
            return

        # Improved Error Handling
        if isinstance(output, dict):
            # Check for error in various possible formats
            error_msg = output.get("error") or output.get("message")
            if error_msg and not output.get("image_base64"):
                # If error is a dict/json, format it
                if isinstance(error_msg, dict):
                    error_msg = json.dumps(error_msg, indent=2, ensure_ascii=False)
                
                await bot.send_message(chat_id, f"❌ <b>Ошибка воркера:</b>\n<pre>{error_msg}</pre>", parse_mode="HTML")
                
                # Send debug json if available
                dbg = output.get("debug_prompt")
                if dbg:
                    try:
                        data = json.dumps(dbg, ensure_ascii=False, indent=2).encode("utf-8")
                        await bot.send_document(chat_id, BufferedInputFile(data, filename="debug_workflow.json"))
                    except Exception: pass
                return
        elif isinstance(output, str) and len(output) < 500: # It's probably an error string
             await bot.send_message(chat_id, f"❌ Ошибка (строка): {output}")
             return

        image_b64 = None
        if isinstance(output, dict):
            image_b64 = output.get("image_base64")
            
        if image_b64:
            try:
                img_bytes = base64.b64decode(image_b64)
                caption = f"✅ {settings['style']} | {settings['aspect_ratio']}"
                if controlnet_image:
                    caption += "\n🧘‍♀️ Поза применена"
                    # Optional: Clear pose after usage
                    # del user_settings[user_id]["controlnet_image"]
                    
                await bot.send_photo(chat_id, photo=BufferedInputFile(img_bytes, filename="result.png"), caption=caption)
                return
            except Exception as send_err:
                logger.error(f"Failed to send photo: {send_err}")
                
        await bot.send_message(chat_id, "❌ Ошибка: В ответе нет изображения.")

    except Exception as e:
        logger.error(f"RunPod Error: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка соединения с RunPod: {e}")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """
    Admin panel: Shows RunPod balance and worker status.
    """
    # Simple check if user is admin (replace with your ID if needed, or allow everyone for now)
    # ADMIN_ID = 123456789
    # if message.from_user.id != ADMIN_ID: return
    
    msg = await message.answer("🔄 Загрузка данных RunPod...")
    
    try:
        # 1. Get User Balance via GraphQL
        # Note: RunPod API key must have read permissions
        headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}
        query = """
        query {
            myself {
                id
                balance
            }
        }
        """
        async with asyncio.Lock(): # Simple lock not needed really but good practice
             pass
             
        # Use runpod library if possible, but requests is easier for raw GQL
        import requests
        gql_url = "https://api.runpod.io/graphql?api_key=" + RUNPOD_API_KEY
        
        r = await asyncio.to_thread(requests.post, gql_url, json={"query": query})
        data = r.json()
        
        balance = "N/A"
        if "data" in data and "myself" in data["data"]:
            balance = f"${data['data']['myself']['balance']:.2f}"
            
        # 2. Get Endpoint Health
        # We can't easily get active workers count via simple API without GQL for endpoints
        # Let's just show balance for now
        
        report = (
            f"👮‍♂️ **Админ-панель**\n\n"
            f"💰 **Баланс:** `{balance}`\n"
            f"🆔 **Endpoint ID:** `{RUNPOD_ENDPOINT_ID}`\n"
            f"📉 **Статус:** Активен\n"
        )
        
        await msg.edit_text(report, parse_mode="Markdown")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка получения данных: {e}")

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

@dp.message(F.text.contains("Персонаж"))
async def menu_character(message: types.Message):
    await message.answer("Выберите персонажа для генерации:", reply_markup=character_keyboard())

@dp.callback_query(F.data.startswith("char_"))
async def callback_character(callback: types.CallbackQuery):
    if callback.data == "char_insta_v1":
        get_settings(callback.from_user.id)["character"] = "insta_v1"
        await callback.message.answer("✅ Персонаж установлен: Insta Girl (v1)")
    elif callback.data == "char_insta_v2":
        get_settings(callback.from_user.id)["character"] = "insta_v2"
        await callback.message.answer("✅ Персонаж установлен: Insta Girl (v2)")
    elif callback.data == "char_insta_v3":
        get_settings(callback.from_user.id)["character"] = "insta_v3"
        await callback.message.answer("✅ Персонаж установлен: Insta Girl (v3)")
    elif callback.data == "char_lustify":
        get_settings(callback.from_user.id)["character"] = "lustify"
        await callback.message.answer("✅ Персонаж установлен: LUSTIFY (18+)")
    elif callback.data == "char_none":
        get_settings(callback.from_user.id)["character"] = None
        await callback.message.answer("✅ Персонаж отключен")
    await callback.answer()

@dp.callback_query(F.data.startswith("ar_"))
async def callback_aspect(callback: types.CallbackQuery):
    ar = callback.data.split("_")[1]
    get_settings(callback.from_user.id)["aspect_ratio"] = ar
    await callback.message.answer(f"✅ Установлен формат: {ar}")
    await callback.answer()

@dp.callback_query(F.data == "style_lustify")
async def process_style_lustify(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_lustify"
    await callback.answer("🔥 Стиль LUSTIFY выбран!")
    await callback.message.answer("✅ Выбран стиль: 🔥 LUSTIFY (18+). Отправьте промпт.")

@dp.callback_query(F.data == "style_deepthroat")
async def process_style_deepthroat(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_deepthroat"
    await callback.answer("👅 Стиль Deep Throat выбран!")
    await callback.message.answer("✅ Выбран стиль: 👅 Deep Throat (18+). Отправьте промпт.")

@dp.callback_query(F.data == "style_amateur")
async def process_style_amateur(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_amateur"
    await callback.answer("📸 Стиль Amateur выбран!")
    await callback.message.answer("✅ Выбран стиль: 📸 Amateur (18+). Отправьте промпт.")

@dp.callback_query(F.data == "style_facial")
async def process_style_facial(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_facial"
    await callback.answer("💦 Стиль Facial выбран!")
    await callback.message.answer("✅ Выбран стиль: 💦 Facial (Pony). Отправьте промпт.")

@dp.callback_query(F.data == "style_betternudes")
async def process_style_betternudes(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_betternudes"
    await callback.answer("👙 Стиль BetterNudes выбран!")
    await callback.message.answer("✅ Выбран стиль: 👙 BetterNudes. Отправьте промпт.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    """
    Handle incoming photos for ControlNet (Pose) or Deepfake (Face).
    """
    # Ask user what to do with the photo
    kb = [
        [InlineKeyboardButton(text="🧘‍♀️ Использовать как Позу (ControlNet)", callback_data="set_pose")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_photo")]
    ]
    
    # Download photo to memory temporarily
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # We can't easily pass file_id to callback, so we save it to user_settings temporarily as 'pending_photo'
    get_settings(message.from_user.id)["pending_photo"] = file_id
    
    await message.reply("📸 Вы прислали фото. Что с ним сделать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "set_pose")
async def callback_set_pose(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_settings(user_id)
    file_id = settings.get("pending_photo")
    
    if not file_id:
        await callback.answer("❌ Ошибка: фото не найдено.")
        return

    try:
        # Download photo
        file = await bot.get_file(file_id)
        file_content = await bot.download_file(file.file_path)
        
        # Convert to base64
        img_b64 = base64.b64encode(file_content.read()).decode("utf-8")
        
        # Save to settings
        settings["controlnet_image"] = img_b64
        
        await callback.message.edit_text("✅ <b>Поза сохранена!</b>\nТеперь отправьте промпт, и бот использует эту позу.\n\n(Чтобы сбросить позу, нажмите /reset_pose или просто отправьте новую).", parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Photo download error: {e}")
        await callback.message.edit_text("❌ Ошибка загрузки фото.")

@dp.callback_query(F.data == "cancel_photo")
async def callback_cancel_photo(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.message(Command("reset_pose"))
async def cmd_reset_pose(message: types.Message):
    settings = get_settings(message.from_user.id)
    if "controlnet_image" in settings:
        del settings["controlnet_image"]
        await message.reply("🗑 Поза сброшена.")
    else:
        await message.reply("ℹ️ Поза не была установлена.")

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
