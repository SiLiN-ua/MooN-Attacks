import asyncio
import os
import json
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

API_ID = int(os.getenv('TELEGRAM_API_ID', 0))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE = os.getenv('TELEGRAM_PHONE', '')

async def main():
    client = TelegramClient(
        os.path.join(BASE_DIR, 'warmap_session'),
        API_ID, API_HASH
    )
    await client.start(phone=PHONE)

    print("Loading your channels and chats...\n")

    channels = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            username = getattr(entity, 'username', None)
            url = f"https://t.me/{username}" if username else None
            channels.append({
                'id': entity.id,
                'name': dialog.name,
                'username': username or '',
                'url': url or '',
                'type': 'channel' if isinstance(entity, Channel) else 'chat',
                'members': getattr(entity, 'participants_count', 0) or 0,
            })

    # Сортуємо за кількістю учасників
    channels.sort(key=lambda x: x['members'], reverse=True)

    # Виводимо список
    print(f"{'#':<4} {'Name':<40} {'Username':<30} {'Members':>8}")
    print("-" * 86)
    for i, ch in enumerate(channels, 1):
        print(f"{i:<4} {ch['name'][:38]:<40} {ch['username'][:28]:<30} {ch['members']:>8}")

    # Зберігаємо в файл
    out = os.path.join(BASE_DIR, 'data', 'my_channels.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(channels)} channels/chats")
    print(f"Saved to: data/my_channels.json")

    await client.disconnect()

asyncio.run(main())
