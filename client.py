import os
import sys
import requests

NEXUS_SERVER_URL = os.getenv("NEXUS_SERVER_URL", "https://your-nexus-app.onrender.com")
NEXUS_KEY = os.getenv("NEXUS_PROJECT_KEY")

def verify_nexus_license():
    if not NEXUS_KEY:
        print("[project NEXUS] ❌ ОШИБКА: Переменная окружения 'NEXUS_PROJECT_KEY' отсутствует.")
        sys.exit(1)
        
    try:
        response = requests.get(f"{NEXUS_SERVER_URL}/validate/{NEXUS_KEY}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"[project NEXUS] ✅ Авторизация успешна! Пользователь: {data['user_id']}. Лицензия до: {data['expires_at']}")
        else:
            detail = response.json().get("detail", "Неизвестная ошибка сервера")
            print(f"[project NEXUS] ❌ Отказано в доступе: {detail}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[project NEXUS] ❌ Ошибка подключения к серверу авторизации: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_nexus_license()
