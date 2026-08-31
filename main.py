import os
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

app = FastAPI(
    title="NEXUS License Server",
    description="Микросервис авторизации и валидации лицензионных ключей для проекта NEXUS",
    version="1.0.0"
)

# Хранилище в памяти (In-Memory) для демонстрации на Render.
# В продакшене замените на базу данных (PostgreSQL / Redis).
# Структура: { hashed_key: {"user_id": str, "expires_at": datetime, "is_active": bool} }
LICENSE_DB = {}
SALT = os.getenv("NEXUS_SALT", "NEXUS_DEFAULT_SECURE_SALT_2026")
ADMIN_TOKEN = os.getenv("NEXUS_ADMIN_TOKEN", "nexus-super-admin-secret-token")

api_key_header = APIKeyHeader(name="X-NEXUS-ADMIN-TOKEN", auto_error=False)

def verify_admin(token: str = Depends(api_key_header)):
    if not token or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный или отсутствующий административный токен")
    return token

class KeyGenerationRequest(BaseModel):
    user_id: str
    days_valid: int = 30

def hash_key(key: str) -> str:
    return hashlib.sha256((key + SALT).encode()).hexdigest()

@app.get("/")
def read_root():
    return {"status": "online", "service": "NEXUS Core Licensing Server"}

@app.post("/admin/generate")
def generate_key(req: KeyGenerationRequest, admin: str = Depends(verify_admin)):
    """Генерация нового лицензионного ключа (Только для Администратора)"""
    raw_token = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    license_key = f"NEXUS-{raw_token}"
    
    expire_date = datetime.utcnow() + timedelta(days=req.days_valid)
    hashed = hash_key(license_key)
    
    LICENSE_DB[hashed] = {
        "user_id": req.user_id,
        "expires_at": expire_date,
        "is_active": True
    }
    
    return {
        "license_key": license_key,
        "user_id": req.user_id,
        "expires_at": expire_date.isoformat(),
        "status": "created"
    }

@app.get("/validate/{license_key}")
def validate_key(license_key: str):
    """Публичный эндпоинт для проверки ключа клиентом NEXUS"""
    hashed = hash_key(license_key)
    
    if hashed not in LICENSE_DB:
        raise HTTPException(status_code=404, detail="Ключ не найден в реестре")
        
    data = LICENSE_DB[hashed]
    
    if not data["is_active"]:
        raise HTTPException(status_code=403, detail="Лицензия деактивирована администратором")
        
    if datetime.utcnow() > data["expires_at"]:
        raise HTTPException(status_code=403, detail="Срок действия лицензии истек")
        
    return {
        "valid": True,
        "user_id": data["user_id"],
        "expires_at": data["expires_at"].isoformat()
    }
