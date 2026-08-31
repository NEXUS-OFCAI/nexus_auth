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

# Чтение переменных из панели Render (пароль теперь сверяется внутри кода)
ADMIN_PASSWORD = os.getenv("NEXUS_ADMIN_TOKEN", "BERSERK2026")
SALT = os.getenv("NEXUS_SALT", "NEXUS_CORE_SALT_2026")

db_premium_keys = {}
ip_audit_log = []

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

# 1. ГЛАВНАЯ СТРАНИЦА
@app.get("/", response_class=HTMLResponse)
async def public_index(request: Request):
    return "<h3>NEXUS Auth Service is running successfully on Render.com</h3>"

# 2. АДМИНКА (Вход через безопасный параметр ?key=)
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, key: str = None):
    """Вход строго по ссылке: /admin?key=BERSERK2026"""
    if key != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2>403 Forbidden: Доступ заблокирован. Неверный ключ администратора.</h2>", status_code=403)
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "admin_password": ADMIN_PASSWORD, 
        "generated_key": None,
        "logs": ip_audit_log[-20:]
    })

# 3. ОБРАБОТЧИК ФОРМЫ
@app.post("/admin/generate", response_class=HTMLResponse)
async def admin_generate_key(request: Request, user_id: str = Form(...), admin_pass: str = Form(...)):
    if admin_pass != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Действие отклонено: сессия устарела")
    
    # Генерация ключа лицензии
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

# 4. ПРОВЕРКА ДЛЯ ВАШИХ ПРОГРАММ
@app.get("/check")
def check_license(key: str, ip: str, request: Request):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "requested_key": key, "client_ip": ip}
    ip_audit_log.append(log_entry)
    
    if key == "nexus_master_owner_key":
        return {"status": "success", "role": "owner", "user_id": "BERSERK"}
        
    hashed = hash_key(key)
    if hashed in db_premium_keys:
        return {"status": "success", "role": "premium", "user_id": db_premium_keys[hashed]["user_id"]}
        
    return JSONResponse(status_code=401, content={"status": "failed", "detail": "Invalid Access Key"})
