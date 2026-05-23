import asyncio
import os
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from dotenv import load_dotenv
from .db import Event, Channel, init_db
from .filter import is_military, get_event_type
from .geo_parser import extract_city

# UTC+3 — Украина (лето) и Россия (МСК)
TZ_LOCAL = timezone(timedelta(hours=3))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

API_ID = int(os.getenv('TELEGRAM_API_ID', 0))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE = os.getenv('TELEGRAM_PHONE', '')

client = None
socketio_ref = None
_monitor_loop = None   # event loop пока работает live-монитор

def get_client():
    global client
    if client is None:
        client = TelegramClient(
            os.path.join(BASE_DIR, 'warmap_session'),
            API_ID, API_HASH
        )
    return client

def set_socketio(sio):
    global socketio_ref
    socketio_ref = sio

async def get_media_url(message, channel_slug=None):
    """Скачивает фото локально, для видео/документов — возвращает ссылку на сообщение"""
    if not message.media:
        return None

    if isinstance(message.media, MessageMediaPhoto):
        try:
            media_dir = os.path.join(BASE_DIR, 'static', 'media')
            os.makedirs(media_dir, exist_ok=True)
            filename = f"{message.id}.jpg"
            path = os.path.join(media_dir, filename)
            if not os.path.exists(path):
                await get_client().download_media(message, file=path)
            return f"/static/media/{filename}"
        except Exception as ex:
            print(f"  [MEDIA] Download failed: {ex}")

    # Для видео/документов — ссылка на сообщение в Telegram
    if channel_slug and message.id:
        return f"https://t.me/{channel_slug}/{message.id}"
    return None

async def process_message(event_msg, channel_name, channel_url):
    """Обробляє повідомлення — фільтрує, геолоцює, зберігає"""
    text = event_msg.text or ''
    if not text:
        return None

    if not is_military(text):
        print(f"  [SKIP] {channel_name}: {text[:60]!r}")
        return None

    city, lat, lon = extract_city(text)
    # Fallback на назву каналу — ТІЛЬКИ назва міста (для фільтрів і відображення).
    # Координати з назви каналу НЕ встановлюємо: канал «Дніпро ЧП» може писати
    # про події в Новоросійську — тоді точка потрапить не туди.
    # Точка на карті = тільки якщо місто знайдено в тексті повідомлення.
    if not city:
        ch_city, _, _ = extract_city(channel_name)
        if ch_city:
            city = ch_city   # лейбл для відображення і фільтрів
            # lat, lon залишаються None → без маркера на карті
    event_type = get_event_type(text)
    channel_slug = channel_url.replace('https://t.me/', '').strip('/')
    media_url = await get_media_url(event_msg, channel_slug)

    # Беремо реальний час повідомлення з Telegram (UTC) → конвертуємо в UTC+3
    msg_time = event_msg.date.astimezone(TZ_LOCAL).replace(tzinfo=None)

    event = Event.create(
        timestamp=msg_time,
        text=text,
        channel_name=channel_name,
        channel_url=channel_url,
        city=city,
        lat=lat,
        lon=lon,
        event_type=event_type,
        media_url=media_url,
        message_id=event_msg.id,
    )

    print(f"  [SAVE] {channel_name} | {event_type} | {city or 'no city'} | {text[:60]!r}")

    result = {
        'id': event.id,
        'timestamp': event.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'text': text[:300],
        'channel_name': channel_name,
        'channel_url': channel_url,
        'city': city,
        'lat': lat,
        'lon': lon,
        'event_type': event_type,
        'media_url': media_url,
        'message_id': event_msg.id,
    }

    # Шлємо в браузер завжди — навіть без координат
    if socketio_ref:
        socketio_ref.emit('new_event', result)

    return result

async def start_monitoring(channels: list):
    """Запускає моніторинг каналів"""
    init_db()
    c = get_client()
    await c.start(phone=PHONE)

    # Збираємо множину username-ів з БД для швидкої перевірки
    watched = set()
    for url in channels:
        slug = url.replace('https://t.me/', '').strip('/')
        if slug and not slug.startswith('+'):
            watched.add(slug.lower())

    # Слухаємо ВСІ повідомлення, фільтруємо в хендлері
    @c.on(events.NewMessage())
    async def handler(event_msg):
        try:
            chat = await event_msg.get_chat()
            username = getattr(chat, 'username', None)
            if not username:
                return
            # Пропускаємо якщо канал не в нашому списку
            if username.lower() not in watched:
                return
            channel_name = getattr(chat, 'title', username)
            channel_url = f"https://t.me/{username}"
            print(f"[MSG] {channel_name} (@{username}): {(event_msg.message.text or '')[:80]!r}")
            await process_message(event_msg.message, channel_name, channel_url)
        except Exception as e:
            print(f"Error processing message: {e}")

    print(f"✓ Monitoring {len(watched)} channels — waiting for messages...")
    await c.run_until_disconnected()

def run_monitor(channels: list, sio=None):
    global _monitor_loop
    set_socketio(sio)
    _monitor_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_monitor_loop)
    try:
        _monitor_loop.run_until_complete(start_monitoring(channels))
    finally:
        _monitor_loop = None


# ===== ЗАВАНТАЖЕННЯ ІСТОРІЇ =====

async def load_history_from_telegram(channels, date_from_str, date_to_str,
                                      cities_filter=None, sio=None, progress_cb=None):
    """Тягне повідомлення з каналів за вказаний період, фільтрує та зберігає"""

    TZ_UTC3 = timezone(timedelta(hours=3))

    # Нормалізуємо — браузер може не передати секунди
    if len(date_from_str) == 16: date_from_str += ':00'
    if len(date_to_str)   == 16: date_to_str   += ':00'

    df = datetime.strptime(date_from_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ_UTC3)
    dt = datetime.strptime(date_to_str,   '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ_UTC3)
    df_utc = df.astimezone(timezone.utc)
    dt_utc = dt.astimezone(timezone.utc) + timedelta(seconds=1)  # inclusive end

    c = get_client()
    if not c.is_connected():
        await c.start(phone=PHONE)

    slugs = [u.replace('https://t.me/', '').strip('/')
             for u in channels
             if u.replace('https://t.me/', '').strip('/') and
             not u.replace('https://t.me/', '').strip('/').startswith('+')]

    saved_total = 0

    for idx, slug in enumerate(slugs):
        channel_url = f'https://t.me/{slug}'

        # Отримуємо назву каналу
        try:
            entity = await c.get_entity(slug)
            channel_name = getattr(entity, 'title', slug)
        except Exception as e:
            print(f'[HISTORY] Can\'t get entity {slug}: {e}')
            channel_name = slug
            entity = slug

        print(f'[HISTORY] [{idx+1}/{len(slugs)}] {channel_name} ...')

        if progress_cb:
            progress_cb(channel_name, idx + 1, len(slugs), saved_total)
        if sio:
            sio.emit('history_progress', {
                'channel': channel_name,
                'current': idx + 1,
                'total':   len(slugs),
                'saved':   saved_total,
            })

        saved_ch = 0
        try:
            async for msg in c.iter_messages(entity, offset_date=dt_utc,
                                              reverse=False, limit=None):
                # Виходимо як тільки пішли раніше старту
                if msg.date < df_utc:
                    break

                text = msg.text or ''
                if not text:
                    continue

                # Дублікати — пропускаємо
                if Event.select().where(
                    (Event.channel_url == channel_url) &
                    (Event.message_id  == msg.id)
                ).exists():
                    continue

                if not is_military(text):
                    continue

                city, lat, lon = extract_city(text)
                # Fallback: лише назва міста з каналу, координати НЕ встановлюємо
                # (щоб «Дніпро ЧП» що пише про Новоросійськ не ставив точку в Дніпрі)
                if not city:
                    ch_city, _, _ = extract_city(channel_name)
                    if ch_city:
                        city = ch_city
                        # lat, lon = None, None (залишаються з extract_city(text) = None)

                # Фільтр маршруту (якщо заданий)
                if cities_filter:
                    txt_l  = text.lower()
                    city_l = (city or '').lower()
                    ch_l   = channel_name.lower()
                    if not any(
                        cf.lower() in txt_l or
                        cf.lower() in city_l or
                        cf.lower() in ch_l
                        for cf in cities_filter
                    ):
                        continue

                event_type = get_event_type(text)
                # Фото не качаємо при завантаженні історії — займає занадто довго
                # Замість цього зберігаємо пряме посилання на повідомлення в Telegram
                media_url = f'https://t.me/{slug}/{msg.id}' if msg.media else None
                msg_time   = msg.date.astimezone(TZ_LOCAL).replace(tzinfo=None)

                event = Event.create(
                    timestamp=msg_time,
                    text=text,
                    channel_name=channel_name,
                    channel_url=channel_url,
                    city=city, lat=lat, lon=lon,
                    event_type=event_type,
                    media_url=media_url,
                    message_id=msg.id,
                )

                saved_ch    += 1
                saved_total += 1

                if sio:
                    sio.emit('history_event', {
                        'id':           event.id,
                        'timestamp':    event.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'text':         text[:300],
                        'channel_name': channel_name,
                        'channel_url':  channel_url,
                        'city': city, 'lat': lat, 'lon': lon,
                        'event_type':   event_type,
                        'media_url':    media_url,
                        'message_id':   msg.id,
                    })

        except Exception as e:
            print(f'[HISTORY] Error reading {slug}: {e}')
            if sio:
                sio.emit('history_error', {'channel': channel_name, 'error': str(e)})

        print(f'[HISTORY]   → {channel_name}: {saved_ch} saved')

    if sio:
        sio.emit('history_done', {'saved': saved_total})

    print(f'[HISTORY] ✅ Done — total {saved_total} events saved')
    return saved_total


def run_load_history(channels, date_from, date_to, cities_filter=None, sio=None, progress_cb=None):
    """Запускає загрузку: якщо монітор працює — підключається до його event loop"""
    global _monitor_loop
    if _monitor_loop and _monitor_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(
            load_history_from_telegram(channels, date_from, date_to,
                                        cities_filter, sio, progress_cb),
            _monitor_loop
        )
        future.result()
    else:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                load_history_from_telegram(channels, date_from, date_to,
                                            cities_filter, sio, progress_cb)
            )
        finally:
            loop.close()
