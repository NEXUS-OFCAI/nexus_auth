import os
import hashlib
import secrets
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="NEXUS Core Headless Auth")

# Считываем настройки из панели Render. По умолчанию пароль: BERSERK2026
ADMIN_PASSWORD = os.getenv("NEXUS_ADMIN_TOKEN", "BERSERK2026")
SALT = os.getenv("NEXUS_SALT", "NEXUS_SYSTEM_SALT_2026")

# Хранилища данных в оперативной памяти сервера
db_premium_keys = {}
ip_audit_log = []

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

# 1. СТАТУС СЕРВЕРА (ГЛАВНАЯ СТРАНИЦА)
@app.get("/")
def health_check():
    return {"status": "online", "system": "NEXUS Core Auth API"}

# 2. ГЕНЕРАЦИЯ КЛЮЧЕЙ ЧЕРЕЗ ССЫЛКУ (Вместо админки)
# URL-формат: /generate?user=ИМЯ&token=BERSERK2026
@app.get("/generate")
def generate_new_license(user: str = None, token: str = None):
    if not user or not token:
        raise HTTPException(status_code=400, detail="Missing fields 'user' or 'token'")
        
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid token")
        
    # Создаем уникальный ключ
    raw_key = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"NEXUS-{raw_key}"
    
    # Хешируем и сохраняем владельца
    hashed = hash_key(license_key)
    db_premium_keys[hashed] = {
        "user_id": user,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return {
        "status": "success",
        "message": f"License created for {user}",
        "license_key": license_key
    }

# 3. ПРОСМОТР ЛОГОВ ПОДКЛЮЧЕНИЙ IP ЧЕРЕЗ ССЫЛКУ
# URL-формат: /logs?token=BERSERK2026
@app.get("/logs")
def view_telemetry_logs(token: str = None):
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid token")
    return {
        "total_connections_checked": len(ip_audit_log),
        "recent_logs": ip_audit_log[-30:] # Последние 30 проверок
    }

# 4. ПРОВЕРКА ДЛЯ ВАШИХ ПРОГРАММ-КЛИЕНТОВ
# URL-формат: /check?key=КЛЮЧ&ip=IP_АДРЕС
@app.get("/check")
def check_client_license(key: str, ip: str):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Логгируем абсолютно каждый запрос (USER CHECK телеметрия)
    log_entry = {"timestamp": timestamp, "requested_key": key, "client_ip": ip}
    ip_audit_log.append(log_entry)
    
    # А. Проверка на Мастер-Ключ создателя
    if key == "nexus_master_owner_key":
        return {"status": "success", "role": "owner", "user_id": "BERSERK"}
        
    # Б. Проверка динамических ключей
    hashed = hash_key(key)
    if hashed in db_premium_keys:
        return {"status": "success", "role": "premium", "user_id": db_premium_keys[hashed]["user_id"]}
        
    return JSONResponse(status_code=401, content={"status": "failed", "detail": "🔒 Access Denied: Invalid Key"})
