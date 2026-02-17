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
class ImportLora(StatesGroup):
    waiting_for_file = State()
    waiting_for_name = State()


# User settings storage (Persistent JSON)
SETTINGS_FILE = "user_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
    return {}

def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(user_settings, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")

user_settings = load_settings()

def get_settings(user_id):
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "aspect_ratio": "9:16", 
            "style": "style_auto",
            "identity_strength": 0.6,
            "custom_loras": {}
        }
        save_settings()
    return user_settings[str(user_id)]

# Helper to save on update
def update_setting(user_id, key, value):
    settings = get_settings(user_id)
    settings[key] = value
    save_settings()



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
        [KeyboardButton(text="👤 Сила сходства (Identity)"), KeyboardButton(text="🎭 Мои Персонажи")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def my_characters_keyboard(user_id):
    settings = get_settings(user_id)
    custom_loras = settings.get("custom_loras", {})
    active_char = settings.get("active_character")
    
    kb = []
    
    # 1. User's Specific Girl (Hardcoded for now as per request)
    # Original
    label_original = "✅ User Girl (Original)" if active_char == "user_girl_civitai" else "👩 User Girl (Original)"
    kb.append([InlineKeyboardButton(text=label_original, callback_data="set_char_user_girl_civitai")])
    
    # New Versions (V10, V7, V5, V2)
    versions = [
        ("V10", "10 Epochs", "user_girl_v10"),
        ("V7", "7 Epochs", "user_girl_v7"),
        ("V5", "5 Epochs", "user_girl_v5"),
        ("V2", "2 Epochs", "user_girl_v2")
    ]
    
    for ver, desc, callback in versions:
        label = f"✅ User Girl ({ver})" if active_char == callback else f"👩 User Girl ({ver} - {desc})"
        kb.append([InlineKeyboardButton(text=label, callback_data=f"set_char_{callback}")])

    if custom_loras:
        for name in custom_loras.keys():
            label = f"✅ {name}" if active_char == name else f"⚪️ {name}"
            kb.append([InlineKeyboardButton(text=label, callback_data=f"set_char_{name}")])
            
    kb.append([InlineKeyboardButton(text="❌ Отключить персонажа", callback_data="set_char_none")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

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

@dp.message(F.text == "🎭 Мои Персонажи")
async def menu_my_characters(message: types.Message):
    await message.answer(
        "🎭 <b>Управление персонажами (LoRA)</b>\n\n"
        "Здесь вы можете выбрать <b>активного персонажа</b>.\n"
        "Когда персонаж активен, его внешность будет автоматически применяться ко всем генерациям.\n\n"
        "💡 Чтобы добавить персонажа, используйте команду /import_lora",
        reply_markup=my_characters_keyboard(message.from_user.id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("set_char_"))
async def callback_set_character(callback: types.CallbackQuery):
    char_name = callback.data.replace("set_char_", "")
    user_id = callback.from_user.id
    settings = get_settings(user_id)
    
    if char_name == "none":
        if "active_character" in settings:
            del settings["active_character"]
        msg = "❌ Персонаж отключен. Теперь генерации будут случайными (или по описанию)."
    elif char_name in ["user_girl_civitai", "user_girl_v10", "user_girl_v7", "user_girl_v5", "user_girl_v2"]:
        settings["active_character"] = char_name
        
        display_names = {
            "user_girl_civitai": "User Girl (Original)",
            "user_girl_v10": "User Girl (V10 - 10 Epochs)",
            "user_girl_v7": "User Girl (V7 - 7 Epochs)",
            "user_girl_v5": "User Girl (V5 - 5 Epochs)",
            "user_girl_v2": "User Girl (V2 - 2 Epochs)"
        }
        name = display_names.get(char_name, char_name)
        msg = f"✅ Персонаж <b>{name}</b> выбран!\nТеперь он будет использоваться во всех генерациях."
    else:
        # Check if LoRA exists
        if "custom_loras" in settings and char_name in settings["custom_loras"]:

            settings["active_character"] = char_name
            msg = f"✅ Персонаж <b>{char_name}</b> выбран!\nТеперь он будет использоваться во всех генерациях."
        else:
            msg = "❌ Ошибка: Персонаж не найден."
            
    save_settings()
    await callback.message.edit_text(
        "🎭 <b>Управление персонажами (LoRA)</b>",
        reply_markup=my_characters_keyboard(user_id)
    )
    await callback.answer(msg)
    if char_name != "none":
        await callback.message.answer(msg, parse_mode="HTML")

@dp.callback_query(F.data == "char_none_info")
async def callback_char_none_info(callback: types.CallbackQuery):
    await callback.answer("Используйте /import_lora для добавления!", show_alert=True)


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
    active_char = settings.get("active_character")
    
    # 1. Hardcoded User Girl (CivitAI)
    # Original
    if active_char == "user_girl_civitai":
        loras.append({
            "name": "User_Specific_Girl.safetensors",
            "strength_model": 1.0,
            "strength_clip": 1.0
        })
        prompt = "dark skin, ebony woman, " + prompt
        logger.info(f"Using Hardcoded User LoRA: User_Specific_Girl.safetensors")
    
    # New Versions
    version_settings = {
        "user_girl_v10": {"file": "Ebony_V10.safetensors", "strength": 0.7, "trigger": "dark skin, ebony woman"}, # Reduced strength
        "user_girl_v7": {"file": "Ebony_V7.safetensors", "strength": 0.8, "trigger": "dark skin, ebony woman"},
        "user_girl_v5": {"file": "Ebony_V5.safetensors", "strength": 0.9, "trigger": "dark skin, ebony woman"},
        "user_girl_v2": {"file": "Ebony_V2.safetensors", "strength": 1.0, "trigger": "dark skin, ebony woman"}
    }
    
    if active_char in version_settings:
        conf = version_settings[active_char]
        lora_filename = conf["file"]
        loras.append({
            "name": lora_filename,
            "strength_model": conf["strength"],
            "strength_clip": 1.0
        })
        # Prepend trigger words to prompt
        prompt = f"{conf['trigger']}, {prompt}"
        logger.info(f"Using Hardcoded User LoRA: {lora_filename} (Strength: {conf['strength']})")
    
    if "custom_loras" in settings:
        for name, url in settings["custom_loras"].items():
            # Apply if explicitly named in prompt OR if it's the active character
            if name in prompt or active_char == name:
                logger.info(f"Using Custom LoRA: {name}")
                
                # Avoid duplicates
                if not any(l["name"] == f"{name}.safetensors" for l in loras):
                    loras.append({
                        "name": f"{name}.safetensors",
                        "url": url,
                        "strength_model": 1.0,
                        "strength_clip": 1.0
                    })
                
                # Add trigger word explicitly if needed
                if name not in prompt:
                    prompt = f"photo of {name} person, {prompt}" # Prepend
                else:
                    prompt = prompt.replace(name, f"photo of {name} person") # Enhance existing

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

        # Polling with 20 minute timeout (1200s) as requested for heavy model downloads
        output = None
        try:
            # We use a long timeout because the first run downloads ~40GB of models
            output = await asyncio.to_thread(run_request.output, timeout=1200) 
            logger.info(f"RunPod raw output: {output}")
        except Exception as poll_err:
            logger.error(f"RunPod Poll Error: {poll_err}")
            await bot.send_message(chat_id, f"⚠️ Превышено время ожидания (20 мин).\nСервер всё еще может скачивать модели. Попробуйте через пару минут.")
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

# --- Training Handlers REMOVED per user request ---

# --- Identity / Settings Handlers ---

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
    update_setting(callback.from_user.id, "identity_strength", strength)
    
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
        update_setting(callback.from_user.id, "character", "insta_v1")
        await callback.message.answer("✅ Персонаж установлен: Insta Girl (v1)")
    elif callback.data == "char_insta_v2":
        update_setting(callback.from_user.id, "character", "insta_v2")
        await callback.message.answer("✅ Персонаж установлен: Insta Girl (v2)")
    elif callback.data == "char_insta_v3":
        update_setting(callback.from_user.id, "character", "insta_v3")
        await callback.message.answer("✅ Персонаж установлен: Insta Girl (v3)")
    elif callback.data == "char_lustify":
        update_setting(callback.from_user.id, "character", "lustify")
        await callback.message.answer("✅ Персонаж установлен: LUSTIFY (18+)")
    elif callback.data == "char_none":
        update_setting(callback.from_user.id, "character", None)
        await callback.message.answer("✅ Персонаж отключен")
    await callback.answer()

@dp.callback_query(F.data.startswith("ar_"))
async def callback_aspect(callback: types.CallbackQuery):
    ar = callback.data.split("_")[1]
    update_setting(callback.from_user.id, "aspect_ratio", ar)
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

@dp.message(ImportLora.waiting_for_file)
async def process_import_lora_file(message: types.Message, state: FSMContext):
    url = ""
    
    # 1. Check if it's a direct link (Text)
    if message.text and (message.text.startswith("http://") or message.text.startswith("https://")):
        url = message.text.strip()
        
        # HuggingFace smart fix: /blob/ -> /resolve/
        if "huggingface.co" in url and "/blob/" in url:
            url = url.replace("/blob/", "/resolve/")

        # CivitAI smart fix: Convert model page URL to download API URL
        if "civitai.com/models/" in url and "/api/download" not in url:
            import re
            # Try to find modelVersionId in query params
            match = re.search(r"[?&]modelVersionId=(\d+)", url)
            if match:
                version_id = match.group(1)
                url = f"https://civitai.com/api/download/models/{version_id}"
                await message.answer(f"💡 Обнаружил ID версии! Преобразовал в ссылку для скачивания:\n{url}")
            else:
                 # If no version ID, warn user
                 await message.reply(
                     "⚠️ <b>Это ссылка на страницу модели!</b>\n\n"
                     "Я не вижу <code>modelVersionId</code> в ссылке.\n"
                     "Пожалуйста, пришлите:\n"
                     "1. Ссылку с параметром <code>?modelVersionId=...</code>\n"
                     "2. ИЛИ прямую ссылку на скачивание (через ПКМ -> Copy Link Address).",
                     parse_mode="HTML"
                 )
                 return
            
        if not url.endswith(".safetensors") and "civitai.com" not in url and "huggingface.co" not in url:
             await message.reply("⚠️ Ссылка должна вести на файл .safetensors (CivitAI/HuggingFace).\nНо я попробую её использовать.")
        
        await state.update_data(lora_url=url)
        await message.answer(
            f"✅ Ссылка принята!\nURL: {url}\n\n"
            "Теперь введите <b>имя персонажа (триггер)</b>, которое будет использоваться в промпте.\n"
            "Например: <code>alex_person</code>",
            parse_mode="HTML"
        )
        await state.set_state(ImportLora.waiting_for_name)
        return

    # 2. Check if it's a file (Document)
    if not message.document:
        await message.reply("❌ Пожалуйста, отправьте файл .safetensors ИЛИ ссылку на него (http...).")
        return

    doc = message.document
    if not doc.file_name.endswith(".safetensors"):
        await message.reply("❌ Это не файл LoRA! Расширение должно быть .safetensors")
        return

    if doc.file_size > 20 * 1024 * 1024: # 20MB limit for Telegram Bot API
        await message.reply(
            "❌ <b>Файл слишком большой (>20MB)</b>\n"
            "Telegram не позволяет ботам скачивать файлы больше 20MB.\n\n"
            "👉 <b>Решение:</b>\n"
            "1. Загрузите файл на облако (Google Drive, transfer.sh, dropmefiles.com)\n"
            "2. Пришлите мне <b>прямую ссылку</b> на скачивание.",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer("⏳ Скачиваю файл...")

    try:
        # Download file
        file_info = await bot.get_file(doc.file_id)
        file_content = await bot.download_file(file_info.file_path)
        
        await status_msg.edit_text("⏳ Загружаю на облако (для RunPod)...")
        
        # Upload to transfer.sh or tmpfiles
        import requests
        
        # 1. Try transfer.sh
        try:
            logger.info(f"Uploading {doc.file_name} to transfer.sh...")
            response = requests.put(
                f'https://transfer.sh/{doc.file_name}', 
                data=file_content.read(),
                timeout=300
            )
            if response.status_code == 200:
                url = response.text.strip()
        except Exception as e:
            logger.error(f"transfer.sh upload failed: {e}")
            
        if not url:
            # 2. Try tmpfiles.org
            try:
                logger.info(f"Uploading {doc.file_name} to tmpfiles.org...")
                file_content.seek(0)
                files = {'file': (doc.file_name, file_content.read())}
                response = requests.post('https://tmpfiles.org/api/v1/upload', files=files, timeout=300)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        url = data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
            except Exception as e:
                logger.error(f"tmpfiles.org upload failed: {e}")
        
        if not url:
            await status_msg.edit_text("❌ Не удалось загрузить файл на сервер. Попробуйте позже.")
            return
            
        await state.update_data(lora_url=url)
        await status_msg.delete()
        
        await message.answer(
            f"✅ Файл загружен!\nURL: {url}\n\n"
            "Теперь введите <b>имя персонажа (триггер)</b>, которое будет использоваться в промпте.\n"
            "Например: <code>alex_person</code>",
            parse_mode="HTML"
        )
        await state.set_state(ImportLora.waiting_for_name)
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        await status_msg.edit_text(f"❌ Ошибка импорта: {e}")
        await state.clear()

@dp.message(ImportLora.waiting_for_name)
async def process_import_lora_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name or " " in name or len(name) > 30:
        await message.reply("❌ Некорректное имя. Используйте одно слово на латинице (например: my_char).")
        return
        
    data = await state.get_data()
    url = data.get("lora_url")
    
    # Save to settings
    user_id = message.from_user.id
    settings = get_settings(user_id)
    if "custom_loras" not in settings:
        settings["custom_loras"] = {}
        
    settings["custom_loras"][name] = url
    save_settings()
    
    await message.answer(
        f"✅ <b>Персонаж '{name}' добавлен!</b>\n\n"
        f"Теперь вы можете использовать его в генерации, добавив <code>{name}</code> в описание.\n"
        f"<i>Примечание: Ссылка временная (14 дней). Сохраните файл .safetensors!</i>",
        parse_mode="HTML"
    )
    await state.clear()

@dp.message(Command("import_lora"))
async def cmd_import_lora(message: types.Message, state: FSMContext):
    await message.answer(
        "📥 <b>Импорт LoRA</b>\n\n"
        "Отправьте мне файл <code>.safetensors</code> (до 20MB) или <b>ссылку</b> на него.\n\n"
        "💡 <b>Рекомендую Hugging Face:</b>\n"
        "1. Загрузите файл на https://huggingface.co/new\n"
        "2. Пришлите мне ссылку на файл (можно просто из адресной строки).",
        parse_mode="HTML"
    )
    await state.set_state(ImportLora.waiting_for_file)

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
        types.BotCommand(command="import_lora", description="Импорт .safetensors"),
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
