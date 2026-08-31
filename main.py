import os
import asyncio
import logging
import hashlib
import secrets
from fastapi import FastAPI, HTTPException, Header, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from openai import OpenAI

# Логирование и конфигурация среды
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_TOKEN = os.getenv("NEXUS_ADMIN_TOKEN", "super_secret_admin_pass")
SALT = os.getenv("NEXUS_SALT", "NEXUS_SECURE_SALT_2026")

ai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
app = FastAPI()

# Папка templates должна лежать в корне проекта рядом с main.py
templates = Jinja2Templates(directory="templates")

bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# Имитация БД: { hashed_key: user_id }
db_keys = {}
active_tg_sessions = {}

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

class KeyGenRequest(BaseModel):
    user_id: str

# --- ЧАСТЬ 1: ВЕБ-САЙТ (АДМИН-ПАНЕЛЬ) ---

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Отображает главную страницу панели генерации."""
    return templates.TemplateResponse("index.html", {"request": request, "generated_key": None, "error": None})

@app.post("/", response_class=HTMLResponse)
async def handle_generate_form(request: Request, user_id: str = Form(...), admin_token: str = Form(...)):
    """Обрабатывает отправку формы с сайта."""
    if admin_token != ADMIN_TOKEN:
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "generated_key": None, 
            "error": "❌ Неверный админ-токен! Доступ к генерации заблокирован."
        })
    
    # Генерация ключа
    raw_token = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"NEXUS-{raw_token}"
    
    hashed = hash_key(license_key)
    db_keys[hashed] = user_id
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "generated_key": license_key, 
        "user_id": user_id,
        "error": None
    })

# --- API ДЛЯ ПРОВЕРКИ (ОСТАВЛЯЕМ ДЛЯ СОВМЕСТИМОСТИ) ---
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
    active_tg_sessions[user_id] = False
    await message.answer(
        "**[project NEXUS]**\n"
        "🔒 Система заблокирована.\n\n"
        "Для активации ИИ-модулей, пожалуйста, отправьте ваш лицензионный ключ в формате `NEXUS-XXXX-XXXX-...`"
    )

@dp.message()
async def handle_messages(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()
    
    if not active_tg_sessions.get(user_id, False):
        if user_text.startswith("NEXUS-"):
            hashed = hash_key(user_text)
            if hashed in db_keys:
                active_tg_sessions[user_id] = True
                await message.answer("**[project NEXUS]**\n✅ Авторизация успешна. Доступ открыт!")
            else:
                await message.answer("❌ Ошибка: Ключ не найден в реестре.")
        else:
            await message.answer("🔒 Доступ отклонен. Пожалуйста, введите валидный ключ.")
        return

    if not ai_client:
        await message.answer("⚠️ Ошибка конфигурации: отсутствует API ключ OpenAI.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "# NEXUS Prompt. Вы общаетесь с инженером."},
                {"role": "user", "content": user_text}
            ]
        )
        await message.answer(response.choices.message.content)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@app.on_event("startup")
async def on_startup():
    if bot:
        asyncio.create_task(dp.start_polling(bot))
