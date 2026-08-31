import os
import hashlib
import secrets
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="NEXUS License Management System")

# Явное указание папки с шаблонами
templates = Jinja2Templates(directory="templates")

# Чтение переменных из панели управления Render
ADMIN_PASSWORD = os.getenv("NEXUS_ADMIN_TOKEN", "BERSERK2026")
SALT = os.getenv("NEXUS_SALT", "NEXUS_CORE_SALT_2026")

# Хранилище в оперативной памяти сервера
db_premium_keys = {}
ip_audit_log = []

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

# --- МАРШРУТ 1: ГЛАВНАЯ СТРАНИЦА (ПРОВЕРКА СТАТУСА) ---
@app.get("/", response_class=HTMLResponse)
async def public_index(request: Request):
    return "<h3>NEXUS Auth Service is running successfully on Render.com</h3>"

# --- МАРШРУТ 2: ПАНЕЛЬ АДМИНИСТРАТОРА (ТОЛЬКО GET) ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, pass=None):
    """Вход строго по ссылке: /admin?pass=BERSERK2026"""
    if pass != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2>403 Forbidden: Доступ заблокирован. Неверный пароль.</h2>", status_code=403)
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "admin_password": ADMIN_PASSWORD, 
        "generated_key": None,
        "logs": ip_audit_log[-20:]
    })

# --- МАРШРУТ 3: ОБРАБОТЧИК ФОРМЫ (ОТДЕЛЬНЫЙ URL) ---
@app.post("/admin/generate", response_class=HTMLResponse)
async def admin_generate_key(request: Request, user_id: str = Form(...), admin_pass: str = Form(...)):
    """Принимает данные из формы и возвращает обновленную страницу"""
    if admin_pass != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Действие отклонено: сессия устарела")
    
    # Генерация ключа
    raw_token = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"NEXUS-{raw_token}"
    
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

# --- МАРШРУТ 4: ПРОВЕРКА ДЛЯ ВАШИХ ПРОГРАММ ---
@app.get("/check")
def check_license(key: str, ip: str, request: Request):
    """Проверка лицензии: /check?key=[KEY]&ip=[IP]"""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Логируем подключение
    log_entry = {"timestamp": timestamp, "requested_key": key, "client_ip": ip}
    ip_audit_log.append(log_entry)
    
    # Сверка мастер-ключа
    if key == "nexus_master_owner_key":
        return {"status": "success", "role": "owner", "user_id": "BERSERK"}
        
    # Сверка динамических ключей
    hashed = hash_key(key)
    if hashed in db_premium_keys:
        return {"status": "success", "role": "premium", "user_id": db_premium_keys[hashed]["user_id"]}
        
    return JSONResponse(status_code=401, content={"status": "failed", "detail": "Invalid Access Key"})
