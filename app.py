import os
import hashlib
import secrets
from datetime import datetime

# Попытка импорта FastAPI. Если библиотек нет, Render установит их через Build Command
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
except ImportError:
    # Заглушка для первичной сборки
    FastAPI = lambda *args, **kwargs: None

app = FastAPI(title="NEXUS Clean Core Auth")

# Считываем токены из панели Render. Дефолтный пароль: BERSERK2026
ADMIN_PASSWORD = os.getenv("NEXUS_ADMIN_TOKEN", "BERSERK2026")
SALT = os.getenv("NEXUS_SALT", "NEXUS_SYSTEM_SALT_2026")

# Хранилище в оперативной памяти инстанса Render
db_premium_keys = {}
ip_audit_log = []

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

# 1. ГЛАВНАЯ СТРАНИЦА (ПРОВЕРКА РАБОТОСПСОБНОСТИ)
@app.get("/")
def health_check():
    return {"status": "online", "system": "NEXUS Clean Core Auth"}

# 2. ВЫПУСК КЛЮЧЕЙ ЧЕРЕЗ БРАУЗЕР (Вместо сайта-админки)
# Формат: /generate?user=ИМЯ&token=BERSERK2026
@app.get("/generate")
def generate_new_license(user: str = None, token: str = None):
    if not user or not token:
        raise HTTPException(status_code=400, detail="Missing parameters 'user' or 'token'")
        
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid token")
        
    # Генерируем ключ формата NEXUS-XXXX-XXXX-XXXX-XXXX
    raw_key = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"NEXUS-{raw_key}"
    
    # Хешируем для безопасности и сохраняем
    hashed = hash_key(license_key)
    db_premium_keys[hashed] = {
        "user_id": user,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return {
        "status": "success",
        "message": f"License successfully generated for {user}",
        "license_key": license_key
    }

# 3. ПРОСМОТР ЛОГОВ IP-АДРЕСОВ В БРАУЗЕРЕ
# Формат: /logs?token=BERSERK2026
@app.get("/logs")
def view_telemetry_logs(token: str = None):
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid token")
    return {
        "total_connections": len(ip_audit_log),
        "recent_logs": ip_audit_log[-30:]  # Показываем последние 30 проверок
    }

# 4. ШЛЮЗ ДЛЯ ПРОВЕРКИ ЛИЦЕНЗИЙ ИЗ ВАШИХ ПРОГРАММ
# Формат: /check?key=КЛЮЧ&ip=IP_ПОЛЬЗОВАТЕЛЯ
@app.get("/check")
def check_client_license(key: str, ip: str):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Логируем подключение (USER CHECK телеметрия)
    log_entry = {"timestamp": timestamp, "requested_key": key, "client_ip": ip}
    ip_audit_log.append(log_entry)
    
    # А. Мастер-ключ создателя (всегда активен)
    if key == "nexus_master_owner_key":
        return {"status": "success", "role": "owner", "user_id": "BERSERK"}
        
    # Б. Проверка созданных в этой сессии ключей
    hashed = hash_key(key)
    if hashed in db_premium_keys:
        return {"status": "success", "role": "premium", "user_id": db_premium_keys[hashed]["user_id"]}
        
    return JSONResponse(status_code=401, content={"status": "failed", "detail": "🔒 Access Denied: Invalid License Key"})
