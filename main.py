import os
import asyncio
import logging
import hashlib
import secrets
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from openai import OpenAI

# 1. Конфигурация логирования и переменных среды
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_TOKEN = os.getenv("NEXUS_ADMIN_TOKEN", "super_secret_admin_pass")
SALT = os.getenv("NEXUS_SALT", "NEXUS_SECURE_SALT_2026")

# Инициализация ИИ-клиента
ai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Инициализация FastAPI и Aiogram
app = FastAPI()
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# Имитация БД: { hashed_key: user_id }
# Временные сессии авторизации в ТГ: { tg_user_id: True/False }
db_keys = {}
active_tg_sessions = {}

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

class KeyGenRequest(BaseModel):
    user_id: str

# --- ЧАСТЬ 1: API УПРАВЛЕНИЯ КЛЮЧАМИ (ДЛЯ ВАС) ---
@app.post("/admin/generate")
def generate_key(req: KeyGenRequest, x_nexus_admin_token: str = Header(None)):
    if x_nexus_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный админ-токен")
    
    raw_token = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"NEXUS-{raw_token}"
    
    hashed = hash_key(license_key)
    db_keys[hashed] = req.user_id
    return {"license_key": license_key, "owner": req.user_id}

@app.get("/validate/{key}")
def validate_key(key: str):
    hashed = hash_key(key)
    if hashed in db_keys:
        return {"status": "success", "user_id": db_keys[hashed]}
    raise HTTPException(status_code=401, detail="Invalid key")

# --- ЧАСТЬ 2: ЛОГИКА ТЕЛЕГРАМ-БОТА ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    active_tg_sessions[user_id] = False  # Сбрасываем авторизацию при старте
    await message.answer(
        "**[project NEXUS]**\n"
        "🔒 Система заблокирована.\n\n"
        "Для активации ваших инженерных и аналитических модулей, пожалуйста, отправьте ваш лицензионный ключ в формате `NEXUS-XXXX-XXXX-...`"
    )

@dp.message()
async def handle_messages(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()
    
    # Если пользователь еще не авторизован — проверяем, прислал ли он ключ
    if not active_tg_sessions.get(user_id, False):
        if user_text.startswith("NEXUS-"):
            hashed = hash_key(user_text)
            if hashed in db_keys:
                active_tg_sessions[user_id] = True
                await message.answer("**[project NEXUS]**\n✅ Авторизация успешна. Доступ к ИИ-ассистенту и макрокомандам открыт!")
            else:
                await message.answer("❌ Ошибка: Ключ не найден в реестре или аннулирован.")
        else:
            await message.answer("🔒 Доступ отклонен. Пожалуйста, введите валидный ключ доступа.")
        return

    # Если авторизован — перенаправляем запрос в OpenAI (NEXUS Prompt)
    if not ai_client:
        await message.answer("⚠️ Ошибка конфигурации сервера: отсутствует API ключ нейросети.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "# NEXUS: Advanced Analytical System Prompt. Вы общаетесь со старшим инженером."},
                {"role": "user", "content": user_text}
            ]
        )
        await message.answer(response.choices.message.content)
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации ответа: {str(e)}")

# --- ИНИЦИАЛИЗАЦИЯ И ЗАПУСК ---
@app.on_event("startup")
async def on_startup():
    if bot:
        # Запуск бота в фоновом режиме (Polling) параллельно с FastAPI веб-сервером
        asyncio.create_task(dp.start_polling(bot))

@app.get("/")
def health_check():
    return {"status": "NEXUS Core is online"}
