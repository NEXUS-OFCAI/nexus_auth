import os
import asyncio
import logging
import hashlib
import secrets
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from openai import OpenAI

# Инициализация логирования
logging.basicConfig(level=logging.INFO)

# Конфигурация среды (Берется из Environment Variables на Render)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_PASSWORD = os.getenv("NEXUS_ADMIN_TOKEN", "MY_SUPER_SECRET_PASSWORD") # Из вашего манифеста
SALT = os.getenv("NEXUS_SALT", "WHYEN_CORE_KRAKEN_2026")

ai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
app = FastAPI(title="WHYEN License Management & AI Control System")
templates = Jinja2Templates(directory="templates")

bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# --- БАЗА ДАННЫХ В ПАМЯТИ (In-Memory) ---
# Хранит динамические премиум ключи: { hashed_key: {"user_id": str, "created_at": str} }
db_premium_keys = {}

# Хранит сессии пользователей в Telegram: { tg_user_id: "free" | "premium" | "owner" }
user_roles = {}

# Логи подключений (framework USER CHECK audit)
ip_audit_log = []

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

# --- СТРУКТУРА ДАННЫХ ДЛЯ API ---
class KeyGenRequest(BaseModel):
    user_id: str

# --- ЧАСТЬ 1: ВЕБ-ИНТЕРФЕЙС И АДМИН-ПАНЕЛЬ ---

@app.get("/", response_class=HTMLResponse)
async def public_index(request: Request):
    """Публичная страница проверки статуса сервера."""
    return "<h3>WHYEN Core API Service is running successfully on Render.com</h3>"

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, pass_token: str = None):
    """Панель администратора. Вход: /admin?pass=MY_SUPER_SECRET_PASSWORD"""
    if pass_token != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2>403 Forbidden: Доступ к панели управления WHYEN заблокирован.</h2>", status_code=403)
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "admin_password": ADMIN_PASSWORD, 
        "generated_key": None,
        "logs": ip_audit_log[-20:] # Показываем последние 20 логов IP
    })

@app.post("/admin/generate", response_class=HTMLResponse)
async def admin_generate_key(request: Request, user_id: str = Form(...), admin_pass: str = Form(...)):
    """Генерация премиум-ключей через админку."""
    if admin_pass != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Действие отклонено")
    
    # Генерация уникального ключа WHYEN-PREMIUM
    raw_token = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"WHYEN-{raw_token}"
    
    hashed = hash_key(license_key)
    db_premium_keys[hashed] = {
        "user_id": user_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "admin_password": ADMIN_PASSWORD, 
        "generated_key": license_key,
        "user_id": user_id,
        "logs": ip_audit_log[-20:]
    })

# --- ЭНДПОИНТ ВАЛИДАЦИИ С ЛОГИРОВАНИЕМ IP (USER CHECK framework) ---
@app.get("/check")
def check_license(key: str, ip: str, request: Request):
    """Эндпоинт: /check?key=[KEY]&ip=[IP]"""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Логируем попытку запроса (Аудит сетевой телеметрии)
    log_entry = {"timestamp": timestamp, "requested_key": key, "client_ip": ip}
    ip_audit_log.append(log_entry)
    
    # 1. Проверка на Мастер-Ключ Владельца
    if key == "whyen_master_owner_key":
        return {"status": "success", "role": "owner", "user_id": "BERSERK"}
        
    # 2. Проверка на Вечный Бесплатный Ключ
    if key == "whyen_free_unlimited":
        return {"status": "success", "role": "free", "user_id": "guest"}
        
    # 3. Проверка Динамических Премиум Ключей
    hashed = hash_key(key)
    if hashed in db_premium_keys:
        return {"status": "success", "role": "premium", "user_id": db_premium_keys[hashed]["user_id"]}
        
    return JSONResponse(status_code=401, content={"status": "failed", "detail": "🔒 Invalid Access Key"})

# --- ЧАСТЬ 2: УПРАВЛЕНИЕ TELEGRAM-БОТОМ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_roles[user_id] = "unauthorized" # Сброс роли при старте
    
    await message.answer(
        "**[WHYEN AI Engine v4.2]**\n"
        "🔒 Инициализирована защитная блокировка среды.\n\n"
        "Доступные режимы авторизации:\n"
        "• Отправьте `whyen_free_unlimited` для Базового режима.\n"
        "• Отправьте ваш персональный ключ `WHYEN-XXXX-...` для Премиум доступа.\n"
        "• Отправьте Мастер-Ключ создателя для уровня Owner."
    )

@dp.message()
async def handle_whyen_chat(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()
    current_role = user_roles.get(user_id, "unauthorized")

    # Процесс авторизации, если роль еще не назначена
    if current_role == "unauthorized":
        # Имитируем запрос к нашему же API эндпоинту валидации
        if user_text == "whyen_master_owner_key":
            user_roles[user_id] = "owner"
            await message.answer("⚡ **Уровень доступа: OWNER (Суверенные привилегии BERSERK активированы)**\nВсе ограничения сняты. Логирование запущено.")
        elif user_text == "whyen_free_unlimited":
            user_roles[user_id] = "free"
            await message.answer("ℹ️ **Уровень доступа: FREE (Базовый режим)**\nДоступно: Общие вопросы, мозговой штурм. Написание кода заблокировано.")
        elif user_text.startswith("WHYEN-"):
            hashed = hash_key(user_text)
            if hashed in db_premium_keys:
                user_roles[user_id] = "premium"
                await message.answer(f"🌟 **Уровень доступа: PREMIUM (Пользователь: {db_premium_keys[hashed]['user_id']})**\nГенерация кода и аналитика разблокированы.")
            else:
                await message.answer("❌ Ключ не найден в реестре Render. Попробуйте еще раз.")
        else:
            await message.answer("🔒 Доступ отклонен. Пожалуйста, пройдите авторизацию ключом.")
        return

    # --- ОБРАБОТКА МАКРОКОМАНД НА ОСНОВЕ РОЛЕЙ ---
    if user_text.startswith("!"):
        if user_text == "help":
            if current_role == "free":
                await message.answer("Доступные команды (FREE): help, upgrade")
            elif current_role == "premium":
                await message.answer("Доступные команды (PREMIUM): help, upgrade, !id, !test, !edit, !rickroll")
            elif current_role == "owner":
                await message.answer("Доступные команды (OWNER): help, upgrade, !id, !test, !edit, !rickroll, !ip, !create, !Rikroll")
            return
            
        # Реализация команды !id (для премиум и овнера)
        if user_text == "!id" and current_role in ["premium", "owner"]:
            await message.answer("🧬 **WHYEN Manifest v2.3.2**\nRepository: https://github.com")
            return
            
        # Защита команд уровня Owner
        if user_text == "!ip" and current_role != "owner":
            await message.answer("❌ Ошибка: Недостаточно прав для выполнения сетевой телеметрии.")
            return
        elif user_text == "!ip" and current_role == "owner":
            # Вывод последнего зафиксированного IP из логов
            if ip_audit_log:
                last_log = ip_audit_log[-1]
                await message.answer(f"🛰️ **Телеметрия последнего подключения:**\nIP: {last_log['client_ip']}\nВремя: {last_log['timestamp']}\nКлюч: {last_log['requested_key']}")
            else:
                await message.answer("🛰️ Логи путей IP в настоящий момент пусты.")
            return

    # --- ОТПРАВКА ЗАПРОСА В НЕЙРОСЕТЬ (С УЧЕТОМ РОЛЕВЫХ ФИЛЬТРОВ) ---
    if current_role == "free":
        # Жесткий фильтр кода для бесплатных пользователей
        trigger_words = ["код", "напиши скрипт", "code", "python", "script", "html"]
        if any(word in user_text.lower() for word in trigger_words):
            await message.answer("❌ **Ошибка генерации:** Написание кода и скриптов заблокировано на уровне FREE. Пожалуйста, обновите лицензию.")
            return

    if not ai_client:
        await message.answer("⚠️ Модуль ИИ отключен: на сервере Render не задан OPENAI_API_KEY.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        # Промт адаптируется под роль
        role_instruction = f"Вы работаете в режиме системы WHYEN AI. Текущий уровень пользователя: {current_role}."
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": role_instruction},
                {"role": "user", "content": user_text}
            ]
        )
        await message.answer(response.choices.message.content)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка вызова нейросети: {str(e)}")

@app.on_event("startup")
async def on_startup():
    if bot:
        asyncio.create_task(dp.start_polling(bot))
