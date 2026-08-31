import os
import hashlib
import secrets
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="NEXUS License Management System")
templates = Jinja2Templates(directory="templates")

# Настройки безопасности из переменных окружения Render
ADMIN_PASSWORD = os.getenv("NEXUS_ADMIN_TOKEN", "MY_SUPER_SECRET_PASSWORD")
SALT = os.getenv("NEXUS_SALT", "NEXUS_CORE_SALT_2026")

# Хранилище ключей в памяти: { hashed_key: {"user_id": str, "created_at": str} }
db_premium_keys = {}

# Хранилище логов IP-адресов
ip_audit_log = []

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

class KeyGenRequest(BaseModel):
    user_id: str

# --- ПУБЛИЧНАЯ СТРАНИЦА И АДМИНКА ---

@app.get("/", response_class=HTMLResponse)
async def public_index(request: Request):
    return "<h3>NEXUS Auth Service is running successfully on Render.com</h3>"

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, pass_token: str = None):
    """Вход в админку: /admin?pass=MY_SUPER_SECRET_PASSWORD"""
    if pass_token != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2>403 Forbidden: Доступ заблокирован.</h2>", status_code=403)
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "admin_password": ADMIN_PASSWORD, 
        "generated_key": None,
        "logs": ip_audit_log[-20:]
    })

@app.post("/admin/generate", response_class=HTMLResponse)
async def admin_generate_key(request: Request, user_id: str = Form(...), admin_pass: str = Form(...)):
    if admin_pass != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Действие отклонено")
    
    # Генерация ключа в формате NEXUS-XXXX-XXXX-XXXX-XXXX
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

# --- ЧИСТЫЙ ЭНДПОИНТ ПРОВЕРКИ С ЛОГИРОВАНИЕМ IP ---
@app.get("/check")
def check_license(key: str, ip: str, request: Request):
    """Проверка ключа программами: /check?key=[KEY]&ip=[IP]"""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Записываем IP в аудит-лог
    log_entry = {"timestamp": timestamp, "requested_key": key, "client_ip": ip}
    ip_audit_log.append(log_entry)
    
    # 1. Мастер-ключ (Владелец)
    if key == "nexus_master_owner_key":
        return {"status": "success", "role": "owner", "user_id": "BERSERK"}
        
    # 2. Обычные динамические ключи
    hashed = hash_key(key)
    if hashed in db_premium_keys:
        return {"status": "success", "role": "premium", "user_id": db_premium_keys[hashed]["user_id"]}
        
    return JSONResponse(status_code=401, content={"status": "failed", "detail": "🔒 Invalid Access Key"})
