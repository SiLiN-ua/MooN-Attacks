"""
Авторизация в Telegram для WarMap.
Запускать в CMD.exe (не VS Code!):
    Z:
    cd WarMap
    python auth_telegram.py
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

API_ID   = int(os.getenv('TELEGRAM_API_ID', 0))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE    = os.getenv('TELEGRAM_PHONE', '')
SESSION  = os.path.join(BASE_DIR, 'warmap_session')

async def main():
    print("=" * 45)
    print("  WarMap — Telegram Auth")
    print("=" * 45)

    # Проверяем .env
    if not API_ID or not API_HASH or not PHONE:
        print("\nОШИБКА: Заполни .env файл!")
        print("  TELEGRAM_API_ID=12345678")
        print("  TELEGRAM_API_HASH=abc123...")
        print("  TELEGRAM_PHONE=+380...")
        return

    print(f"\nAPI_ID : {API_ID}")
    print(f"PHONE  : {PHONE}")

    # Принудительно удаляем старую сессию
    for ext in ['', '.session', '.session-journal']:
        path = SESSION + ext
        if os.path.exists(path):
            os.remove(path)
            print(f"Удалена старая сессия: {os.path.basename(path)}")

    print("\nПодключение к Telegram...")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    print("Отправляю запрос кода...")
    try:
        sent = await client.send_code_request(PHONE)
        code_type = type(sent.type).__name__
        print(f"\n✓ Код отправлен!")
        print(f"  Тип доставки: {code_type}")
        if 'App' in code_type:
            print("  >>> Код придёт СООБЩЕНИЕМ в приложении Telegram")
            print(f"  >>> Открой Telegram на устройстве где залогинен {PHONE}")
            print("  >>> Там будет сообщение от 'Telegram' с кодом")
        elif 'Sms' in code_type:
            print("  >>> Код придёт SMS-кой на номер", PHONE)
        elif 'Call' in code_type:
            print("  >>> Будет звонок на номер", PHONE)
        else:
            print(f"  >>> Проверь все устройства с номером {PHONE}")
    except FloodWaitError as e:
        print(f"\nFLOOD WAIT! Telegram заблокировал на {e.seconds} секунд ({e.seconds//60} мин).")
        print("Подожди и попробуй снова.")
        await client.disconnect()
        return
    except Exception as e:
        print(f"\nОшибка при отправке кода: {e}")
        await client.disconnect()
        return

    print()

    code = input("Введи код: ").strip()

    try:
        await client.sign_in(PHONE, code)
    except SessionPasswordNeededError:
        print("Требуется 2FA пароль:")
        password = input("Пароль: ").strip()
        await client.sign_in(password=password)
    except Exception as e:
        print(f"\nОшибка входа: {e}")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"\n✓ Авторизован как: {me.first_name} {me.last_name or ''} (@{me.username or 'нет'})")
    print("✓ Сессия сохранена в warmap_session.session")
    print("\nТеперь запусти:")
    print("  python export_channels.py   — список твоих каналов")
    print("  python app.py               — запустить WarMap")

    await client.disconnect()


asyncio.run(main())
