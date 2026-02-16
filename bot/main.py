import asyncio
import logging
import os
import runpod
import json
import base64
import requests
from deep_translator import GoogleTranslator
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
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

# FSM States
class TrainFace(StatesGroup):
    waiting_for_name = State()
    waiting_for_photos = State()

# User settings storage (in-memory for now)
# Format: {user_id: {"aspect_ratio": "9:16", "style": "Realistic"}}
user_settings = {}

def get_settings(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = {
            "aspect_ratio": "9:16", 
            "style": "Realistic",
            "identity_strength": 0.6 # Default balanced identity
        }
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
        [KeyboardButton(text="📐 Формат"), KeyboardButton(text="🎨 Стиль")],
        [KeyboardButton(text="👤 Сила сходства (Identity)")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def identity_keyboard():
    kb = [
        [InlineKeyboardButton(text="🎨 Слабое (0.3) - Творческий", callback_data="id_str_0.3")],
        [InlineKeyboardButton(text="⚖️ Среднее (0.6) - Баланс", callback_data="id_str_0.6")],
        [InlineKeyboardButton(text="🧬 Сильное (0.8) - Копия", callback_data="id_str_0.8")],
        [InlineKeyboardButton(text="🤖 Максимум (1.0) - Жесткое", callback_data="id_str_1.0")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

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
        [InlineKeyboardButton(text="🤖 Smart Mode (Авто-выбор)", callback_data="style_auto")],
        [InlineKeyboardButton(text="🔥 Lustify", callback_data="style_lustify")],
        [InlineKeyboardButton(text="👅 Deep Throat Глубокая глотка", callback_data="style_deepthroat")],
        [InlineKeyboardButton(text="📸 Amateur Любительское", callback_data="style_amateur")],
        [InlineKeyboardButton(text="💦 Facial Сперма на лице", callback_data="style_facial")],
        [InlineKeyboardButton(text="👙 Better Nudes Реалистичное ню", callback_data="style_betternudes")],
        [InlineKeyboardButton(text="🍆 Futa Футанари", callback_data="style_futa")],
        [InlineKeyboardButton(text="🍑 Butt Plug Анальная пробка", callback_data="style_buttplug")],
        [InlineKeyboardButton(text="🍑 Anal Missionary Анал Миссионерская", callback_data="style_anal_missionary")],
        [InlineKeyboardButton(text="🍑 Anal Abuse Грубый Анал", callback_data="style_anal_abuse")],
        [InlineKeyboardButton(text="🍑 Perfect Anal Идеальный Анал", callback_data="style_perfect_anal")],
        [InlineKeyboardButton(text="🍒 Perfect Breasts Идеальная Грудь", callback_data="style_perfect_breasts")],
        [InlineKeyboardButton(text="🍒 Skin Details Детали Кожи", callback_data="style_ultrareal_breasts")]
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
    
    # Translate prompt from Russian to English if needed
    try:
        # Detect is hard to rely on for short texts, but we can just force translation to 'en'
        # GoogleTranslator handles 'auto' source well.
        translated_prompt = GoogleTranslator(source='auto', target='en').translate(prompt)
        if translated_prompt != prompt:
             logger.info(f"Translated prompt: '{prompt}' -> '{translated_prompt}'")
             await bot.send_message(chat_id, f"🇬🇧 Перевод: <i>{translated_prompt}</i>", parse_mode="HTML")
             prompt = translated_prompt
    except Exception as trans_err:
        logger.error(f"Translation failed: {trans_err}")
        # Continue with original prompt if translation fails
        pass

    # Character LoRA Logic
    loras = []
    char_prefix = ""

    # Check Custom User LoRAs (from /train_face)
    if "custom_loras" in settings:
        for name, url in settings["custom_loras"].items():
            if name in prompt:
                logger.info(f"Using Custom LoRA: {name}")
                loras.append({
                    "name": f"{name}.safetensors",
                    "url": url,
                    "strength_model": 1.0,
                    "strength_clip": 1.0
                })
                # Add trigger word explicitly if needed, but usually it's in the prompt
                prompt = prompt.replace(name, f"photo of {name} person") # Enhance prompt

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
    elif settings["style"] == "style_lustify":
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

    elif settings["style"] == "style_futa":
        # Realistic Futa/Trans Trigger Words
        final_prompt += ", shemself, intersex, futanari, futa, 1girl, penis, erection"
        # Add LoRA to request
        loras.append({
            "name": "RealisticFutaTrans_v1.safetensors",
            "strength_model": 1.0,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_buttplug":
        # Butt Plug Under Thong Trigger Words
        final_prompt += ", butt plug under thong, butt plug next to thong, from behind, ass, thong"
        # Add LoRA to request
        loras.append({
            "name": "ButtPlugUnderThong_v075.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_anal_missionary":
        final_prompt += ", SIDEMISSIONAYANAL, SIDEMISSIONAYANALQUIRON, missionary, sex, anal sex, vaginal sex, penis in pussy, penis in ass"
        loras.append({
            "name": "AnalSideMissionary_Pony_v1.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_anal_abuse":
        final_prompt += ", anal abuse, creampie, gaping, spreading ass, pain, moneyshot, rough sex"
        loras.append({
            "name": "AnalAbuse_v1.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_perfect_anal":
        final_prompt += ", 4N4L, ANAL, PENIS IN ANAL, ass focus, from behind"
        loras.append({
            "name": "PerfectAnal_Pony_v1.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_perfect_breasts":
        final_prompt += ", perfect breasts, round breasts, perky breasts, full breasts, cleavage"
        loras.append({
            "name": "PerfectBreasts_v2.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })

    elif settings["style"] == "style_ultrareal_breasts":
        final_prompt += ", CLOSE UP, SKIN DETAIL, NIPPLE BUMPS, SAGGY BREASTS, high detailed skin"
        loras.append({
            "name": "UltraRealBreastDetailer_v2.safetensors",
            "strength_model": 0.8,
            "strength_clip": 1.0
        })
    elif settings["style"] == "style_auto":
        # Smart Mode: Detect keywords and apply LoRAs automatically
        p = final_prompt.lower()
        
        # 1. Better Cum (New) - Priority for cum shots
        if any(w in p for w in ["cum", "sperm", "facial", "covered in cum", "creampie"]):
            final_prompt += ", CUM, CUM ON FACE, CUM ON BODY, COVERED IN CUM"
            loras.append({"name": "BetterCum_Pony_v1.safetensors", "strength_model": 0.8, "strength_clip": 1.0})
            
        # 2. Deep Throat
        if any(w in p for w in ["deep throat", "blowjob", "sucking", "mouth"]):
            final_prompt += ", GIVING A DEEP THROAT BLOWJOB, saliva, messy face"
            loras.append({"name": "DeepThroatXL_v1.safetensors", "strength_model": 0.6, "strength_clip": 1.0})
            
        # 3. Anal
        if "anal" in p or "ass" in p:
            if "missionary" in p:
                 loras.append({"name": "AnalSideMissionary_Pony_v1.safetensors", "strength_model": 0.8, "strength_clip": 1.0})
            elif "pain" in p or "rough" in p:
                 loras.append({"name": "AnalAbuse_v1.safetensors", "strength_model": 0.8, "strength_clip": 1.0})
            else:
                 loras.append({"name": "PerfectAnal_Pony_v1.safetensors", "strength_model": 0.8, "strength_clip": 1.0})
        
        # 4. Breasts
        if "breasts" in p or "tits" in p or "boobs" in p:
            loras.append({"name": "PerfectBreasts_v2.safetensors", "strength_model": 0.8, "strength_clip": 1.0})
            
        # 5. Nudes (General)
        if any(w in p for w in ["nude", "naked", "strip"]):
            loras.append({"name": "PhotoRealBetterNudes_v3.safetensors", "strength_model": 0.8, "strength_clip": 1.0})
            
        # 6. Futa
        if "futa" in p or "dickgirl" in p:
             loras.append({"name": "RealisticFutaTrans_v1.safetensors", "strength_model": 1.0, "strength_clip": 1.0})

    elif settings["style"] == "Anime":
        final_prompt += ", (anime style, 2d, flat color, illustration)"

    try:
        # Check if user has a pose image or face swap image
        controlnet_image = settings.get("controlnet_image")
        face_swap_image = settings.get("face_swap_image")
            
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
                "identity_strength": settings.get("identity_strength", 0.6),
                "seed": 0,
                "negative_prompt": "headwear, helmet, goggles, weird object on head, (worst quality, low quality:1.4), text, watermark, blur, deformed, painting, cartoon, ugly, bad anatomy, deformed hands, extra fingers",
                "highres_fix": True,
                "controlnet_image": controlnet_image, # Renamed from face_image to controlnet_image for clarity (requires backend update)
                "face_swap_image": face_swap_image, # New field for ReActor
                "loras": loras
            }
        }
        
        status_msg = f"⏳ Запуск генерации...\n⚙️ {settings['aspect_ratio']} | {settings['style']}"
        if controlnet_image:
            status_msg += "\n🧘‍♀️ Используется поза"
        if face_swap_image:
            status_msg += "\n👤 Используется Deepfake (Лицо)"
            
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
                if face_swap_image:
                    caption += "\n👤 Лицо заменено"
                    
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

# --- Training Handlers ---

@dp.message(Command("train_face"))
async def cmd_train_face(message: types.Message, state: FSMContext):
    """Start the face training process"""
    await state.set_state(TrainFace.waiting_for_name)
    await message.answer(
        "🧠 <b>Обучение персональной LoRA</b>\n\n"
        "Я могу обучить модель на вашем лице. Это займет около 10-15 минут.\n\n"
        "📸 <b>Требования к фото (15-30 шт):</b>\n"
        "• 5-7 фото анфас (прямо)\n"
        "• 5-7 фото в пол-оборота\n"
        "• 3-5 фото в профиль\n"
        "• Разные эмоции (улыбка, серьезное)\n"
        "• Разное освещение и фон\n"
        "❌ Без очков, масок и других людей в кадре\n\n"
        "Для начала, придумайте <b>имя персонажа</b> (на латинице, одним словом).\n"
        "<i>Например: alex, elena, my_boss</i>",
        parse_mode="HTML"
    )

@dp.message(TrainFace.waiting_for_name)
async def process_train_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name.replace("_", "").isalnum() or not name.isascii():
        await message.reply("❌ Имя должно содержать только латинские буквы и цифры (без пробелов). Попробуйте еще раз.")
        return
    
    await state.update_data(name=name, photos=[])
    await state.set_state(TrainFace.waiting_for_photos)
    
    kb = [[InlineKeyboardButton(text="✅ Готово / Начать обучение", callback_data="train_start")]]
    
    await message.answer(
        f"👍 Отлично, персонаж будет называться: <b>{name}</b>\n\n"
        "Теперь отправьте мне <b>15-30 фотографий</b> этого человека.\n"
        "Требования:\n"
        "• Разные ракурсы (анфас, профиль, пол-оборота)\n"
        "• Разные эмоции (улыбка, серьезное лицо)\n"
        "• Хорошее освещение, без очков и масок\n"
        "• Желательно квадратные (1:1)\n\n"
        "📸 <i>Вы можете прислать их по одной, группой или архивом ZIP.</i>\n"
        "Как закончите — нажмите кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )

@dp.message(TrainFace.waiting_for_photos, F.photo)
async def process_train_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    # Get the largest photo
    photo = message.photo[-1]
    photos.append({"file_id": photo.file_id, "type": "photo"})
    
    await state.update_data(photos=photos)
    
    # Confirmation every 5 photos or when ready
    if len(photos) % 5 == 0 or len(photos) >= 15:
        kb = [[InlineKeyboardButton(text=f"🚀 Начать ({len(photos)} фото)", callback_data="train_start")]]
        await message.answer(f"📥 Загружено фото: {len(photos)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(TrainFace.waiting_for_photos, F.document)
async def process_train_document(message: types.Message, state: FSMContext):
    # Check if it's an image or zip
    doc = message.document
    mime = doc.mime_type or ""
    
    data = await state.get_data()
    photos = data.get("photos", [])

    if "image" in mime:
        photos.append({"file_id": doc.file_id, "type": "doc_image"})
        await state.update_data(photos=photos)
        msg_text = f"📥 Документ (фото) принят. Всего: {len(photos)}"
    elif "zip" in mime or doc.file_name.endswith(".zip"):
        photos.append({"file_id": doc.file_id, "type": "zip"})
        await state.update_data(photos=photos)
        msg_text = f"📦 ZIP-архив принят. Всего файлов: {len(photos)}"
    else:
        await message.reply("❌ Пожалуйста, присылайте только фото (JPG/PNG) или ZIP-архив.")
        return

    kb = [[InlineKeyboardButton(text=f"🚀 Начать ({len(photos)} фото)", callback_data="train_start")]]
    await message.reply(msg_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "train_start")
async def process_start_training(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    photos = data.get("photos", [])
    
    if not photos:
        await callback.answer("❌ Вы не загрузили ни одного фото!", show_alert=True)
        return
        
    await callback.message.edit_text(
        f"⏳ <b>Подготовка к обучению...</b>\n"
        f"Персонаж: {name}\n"
        f"Файлов: {len(photos)}\n\n"
        "Скачиваю фото и формирую датасет. Это займет минуту...",
        parse_mode="HTML"
    )
    
    # Download photos logic would go here
    # Since we are in a serverless environment (bot might be local or on a VPS), we need to gather these
    # and send them to the worker.
    # For now, we'll collect URLs or download them.
    
    # Create a task to handle download and request
    asyncio.create_task(run_training_task(callback.message.chat.id, callback.from_user.id, name, photos, state))
    await callback.answer()

async def run_training_task(chat_id, user_id, name, photos, state: FSMContext):
    try:
        # 1. Download all photos into a buffer (ZIP)
        import io
        import zipfile
        
        zip_buffer = io.BytesIO()
        
        # Limit to 30 photos to prevent abuse/memory issues
        photos = photos[:30]
        
        status_msg = await bot.send_message(chat_id, f"📥 Скачиваю {len(photos)} фото...")
        
        count = 0
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for i, p in enumerate(photos):
                if i % 5 == 0:
                     try:
                         await bot.edit_message_text(text=f"📥 Скачиваю фото {i+1}/{len(photos)}...", chat_id=chat_id, message_id=status_msg.message_id)
                     except: pass
                
                try:
                    file_info = await bot.get_file(p["file_id"])
                    file_content = await bot.download_file(file_info.file_path)
                    
                    if p["type"] == "zip":
                        # Extract zip content and add to our zip
                        # Need to read content into memory first
                        content_bytes = file_content.read()
                        with zipfile.ZipFile(io.BytesIO(content_bytes)) as input_zip:
                            for file_name in input_zip.namelist():
                                # Filter only images to avoid garbage
                                if file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                    # Use a flat name to avoid directory issues
                                    clean_name = os.path.basename(file_name)
                                    zf.writestr(f"ext_{i}_{clean_name}", input_zip.read(file_name))
                    else:
                         zf.writestr(f"image_{i}.jpg", file_content.read())
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to download photo {i}: {e}")
        
        zip_buffer.seek(0)
        # zip_b64 = base64.b64encode(zip_buffer.getvalue()).decode("utf-8")
        
        # Upload to transfer.sh (Temporary storage to avoid payload limits)
        await bot.edit_message_text(text="☁️ Загружаю архив на сервер...", chat_id=chat_id, message_id=status_msg.message_id)
        
        dataset_url = None
        try:
            # Use asyncio to run synchronous requests in a thread
            def upload_dataset():
                # 1. Try transfer.sh (PUT - more reliable for large files)
                try:
                    logger.info("Uploading to transfer.sh...")
                    response = requests.put(
                        f'https://transfer.sh/{name}_dataset.zip', 
                        data=zip_buffer.getvalue(),
                        timeout=180 # 3 minutes timeout
                    )
                    if response.status_code == 200:
                        url = response.text.strip()
                        if url.startswith("http"): return url
                except Exception as e:
                    logger.error(f"transfer.sh failed: {e}")

                # 2. Try file.io (Fallback)
                try:
                    logger.info("Uploading to file.io...")
                    # file.io expects 'file' field in multipart form
                    files = {'file': (f'{name}_dataset.zip', zip_buffer.getvalue())}
                    response = requests.post('https://file.io', files=files, timeout=180)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("success"): return data.get("link")
                except Exception as e:
                    logger.error(f"file.io failed: {e}")
                
                # 3. Try tmpfiles.org (Second Fallback)
                try:
                    logger.info("Uploading to tmpfiles.org...")
                    files = {'file': (f'{name}_dataset.zip', zip_buffer.getvalue())}
                    response = requests.post('https://tmpfiles.org/api/v1/upload', files=files, timeout=180)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("status") == "success":
                            # Convert to direct download link
                            url = data["data"]["url"]
                            return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                except Exception as e:
                    logger.error(f"tmpfiles.org failed: {e}")

                raise Exception("All upload services failed")
            
            dataset_url = await asyncio.to_thread(upload_dataset)
            logger.info(f"Dataset uploaded to: {dataset_url}")
        except Exception as up_err:
            logger.error(f"Upload failed: {up_err}")
            await bot.send_message(chat_id, f"❌ Не удалось загрузить датасет ({up_err}). Попробуйте меньше фото.")
            return

        # 2. Send to RunPod
        endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
        
        payload = {
            "input": {
                "operation": "train_lora",
                "lora_name": name,
                "dataset_url": dataset_url, # Changed from base64
                "user_id": user_id 
            }
        }
        
        await bot.delete_message(chat_id, status_msg.message_id)
        await bot.send_message(chat_id, "🚀 <b>Запуск обучения на GPU...</b>\nОжидайте, это может занять 10-20 минут.", parse_mode="HTML")
        await state.clear() # Clear state
        
        # Run Async
        run_request = endpoint.run(payload)
        
        # Wait for result (Long timeout for training)
        # RunPod serverless usually times out after 300s-600s in the http request, but execution continues.
        # We need to poll properly.
        
        output = await asyncio.to_thread(run_request.output, timeout=1200) # 20 mins
        
        if output and "lora_url" in output:
            # Success
            lora_url = output["lora_url"]
            
            # Save to user settings
            settings = get_settings(user_id)
            if "custom_loras" not in settings:
                settings["custom_loras"] = {}
            settings["custom_loras"][name] = lora_url
            
            await bot.send_message(chat_id, f"✅ <b>Обучение завершено!</b>\nLoRA создана: {name}\n\nТеперь вы можете использовать её, указав имя <code>{name}</code> в промпте.\n\n⚠️ <b>ВАЖНО:</b>\nСсылка на модель временная (14 дней). Сейчас я отправлю вам сам файл .safetensors. <b>Сохраните его!</b> Если ссылка перестанет работать, вы сможете загрузить файл снова.", parse_mode="HTML")
            
            # Download and send the file to user as backup
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(lora_url) as resp:
                        if resp.status == 200:
                            from aiogram.types import BufferedInputFile
                            file_data = await resp.read()
                            input_file = BufferedInputFile(file_data, filename=f"{name}.safetensors")
                            await bot.send_document(chat_id, input_file, caption=f"📦 Ваш файл модели: {name}.safetensors\nСохраните его надежно!")
            except Exception as e:
                logger.error(f"Failed to send LoRA file: {e}")
                await bot.send_message(chat_id, f"⚠️ Не удалось отправить файл в чат ({e}). Но ссылка работает!")
            
        elif output and "error" in output:
             await bot.send_message(chat_id, f"❌ Ошибка обучения: {output['error']}")
        else:
             await bot.send_message(chat_id, "⚠️ Обучение завершилось, но результат не получен.")
             
    except Exception as e:
        logger.error(f"Training failed: {e}")
        await bot.send_message(chat_id, f"❌ Критическая ошибка: {e}")
        await state.clear()

async def menu_identity(message: types.Message):
    current = get_settings(message.from_user.id).get("identity_strength", 0.6)
    await message.answer(
        f"👤 <b>Настройка силы сходства (IPAdapter)</b>\n"
        f"Текущее значение: <b>{current}</b>\n\n"
        "Чем выше значение, тем больше лицо похоже на оригинал, но меньше свободы для эмоций и стиля.\n"
        "Рекомендуется: <b>0.6 (Баланс)</b>",
        reply_markup=identity_keyboard(),
        parse_mode="HTML"
    )

@dp.message(F.text.contains("Сила сходства"))
async def show_identity_menu(message: types.Message):
    await menu_identity(message)

@dp.callback_query(F.data.startswith("id_str_"))
async def callback_identity(callback: types.CallbackQuery):
    strength = float(callback.data.split("_")[2])
    get_settings(callback.from_user.id)["identity_strength"] = strength
    
    desc = "Баланс"
    if strength <= 0.3: desc = "Творческий"
    elif strength >= 0.8: desc = "Копия"
    
    await callback.message.edit_text(f"✅ Установлена сила сходства: <b>{strength} ({desc})</b>", parse_mode="HTML")
    await callback.answer()

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

@dp.callback_query(F.data == "style_auto")
async def process_style_auto(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_auto"
    await callback.answer("🤖 Smart Mode активирован!")
    await callback.message.answer(
        "✅ <b>Smart Mode активирован!</b>\n"
        "Теперь я сам пойму, какой стиль использовать, исходя из вашего описания.\n"
        "Просто пишите, что хотите увидеть (например: 'cum on face', 'deep throat', 'anal').",
        parse_mode="HTML"
    )

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

@dp.callback_query(F.data == "style_futa")
async def process_style_futa(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_futa"
    await callback.answer("🍆 Стиль Futa/Trans выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍆 Futa/Trans (Pony). Отправьте промпт.")

@dp.callback_query(F.data == "style_buttplug")
async def process_style_buttplug(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_buttplug"
    await callback.answer("🍑 Стиль Butt Plug выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍑 Butt Plug. Отправьте промпт.")

@dp.callback_query(F.data == "style_anal_missionary")
async def process_style_anal_missionary(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_anal_missionary"
    await callback.answer("🍑 Anal Missionary выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍑 Anal Missionary. Отправьте промпт.")

@dp.callback_query(F.data == "style_anal_abuse")
async def process_style_anal_abuse(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_anal_abuse"
    await callback.answer("🍑 Anal Abuse выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍑 Anal Abuse (Rough). Отправьте промпт.")

@dp.callback_query(F.data == "style_perfect_anal")
async def process_style_perfect_anal(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_perfect_anal"
    await callback.answer("🍑 Perfect Anal выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍑 Perfect Anal. Отправьте промпт.")

@dp.callback_query(F.data == "style_perfect_breasts")
async def process_style_perfect_breasts(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_perfect_breasts"
    await callback.answer("🍒 Perfect Breasts выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍒 Perfect Breasts. Отправьте промпт.")

@dp.callback_query(F.data == "style_ultrareal_breasts")
async def process_style_ultrareal_breasts(callback: types.CallbackQuery):
    get_settings(callback.from_user.id)["style"] = "style_ultrareal_breasts"
    await callback.answer("🍒 UltraReal Details выбран!")
    await callback.message.answer("✅ Выбран стиль: 🍒 UltraReal Details. Отправьте промпт.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    """
    Handle incoming photos for ControlNet (Pose) or Deepfake (Face).
    """
    # Ask user what to do with the photo
    kb = [
        [InlineKeyboardButton(text="👤 Использовать как Лицо (Deepfake)", callback_data="set_face")],
        [InlineKeyboardButton(text="🧘‍♀️ Использовать как Позу (ControlNet)", callback_data="set_pose")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_photo")]
    ]
    
    # Download photo to memory temporarily
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # We can't easily pass file_id to callback, so we save it to user_settings temporarily as 'pending_photo'
    get_settings(message.from_user.id)["pending_photo"] = file_id
    
    await message.reply("📸 Вы прислали фото. Что с ним сделать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "set_face")
async def callback_set_face(callback: types.CallbackQuery):
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
        settings["face_swap_image"] = img_b64
        
        await callback.message.edit_text(
            "✅ <b>Лицо сохранено!</b>\n"
            "Теперь при каждой генерации это лицо будет накладываться на персонажа (Deepfake).\n\n"
            "(Чтобы сбросить лицо, используйте команду /reset_face)", 
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Photo download error: {e}")
        await callback.message.edit_text("❌ Ошибка загрузки фото.")

@dp.message(Command("reset_face"))
async def cmd_reset_face(message: types.Message):
    settings = get_settings(message.from_user.id)
    if "face_swap_image" in settings:
        del settings["face_swap_image"]
        await message.reply("🗑 Лицо сброшено.")
    else:
        await message.reply("ℹ️ Лицо не было установлено.")

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
    
    # Set bot commands
    commands = [
        types.BotCommand(command="start", description="Начать работу"),
        types.BotCommand(command="help", description="Инструкция"),
        types.BotCommand(command="train_face", description="Обучить LoRA на лице"),
        types.BotCommand(command="id", description="Показать ваш user id"),
        types.BotCommand(command="reset_face", description="Сбросить лицо (Deepfake)"),
        types.BotCommand(command="reset_pose", description="Сбросить позу")
    ]
    await bot.set_my_commands(commands)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
