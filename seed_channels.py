"""
Завантажує Telegram канали в БД WarMap.

Варіант 1 — автоматичний:
  Якщо вже запускав export_channels.py і є data/my_channels.json,
  скрипт завантажить ВСІ твої канали.

Варіант 2 — дефолтний:
  Якщо my_channels.json немає — завантажить список популярних
  публічних каналів моніторингу (підходить для старту).

Запуск:
  python seed_channels.py
"""

import os
import json
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.db import init_db, Channel

# ===== ПОПУЛЯРНІ ПУБЛІЧНІ КАНАЛИ ДЛЯ СТАРТУ =====
DEFAULT_CHANNELS = [
    # --- Україна: оперативні зведення ---
    ('https://t.me/operativnoua',          'Оперативно UA'),
    ('https://t.me/ukrainenow',            'Ukraine Now'),
    ('https://t.me/UkraineWarMonitor',     'Ukraine War Monitor'),
    ('https://t.me/air_alert_ua',          'Повітряна тривога UA'),
    ('https://t.me/kpszsu',                'Командування ПС ЗСУ'),
    ('https://t.me/kyiv_operativ',         'Київ Оперативний'),
    ('https://t.me/kharkiv_monitoring',    'Харків Моніторинг'),
    ('https://t.me/dnipro_operativ',       'Дніпро Оперативно'),
    ('https://t.me/odessa_operativ',       'Одеса Оперативно'),
    ('https://t.me/kherson_online',        'Херсон Online'),
    ('https://t.me/zaporizhzhia_online',   'Запоріжжя Online'),
    ('https://t.me/sumy_npu',              'Суми НПУ'),
    ('https://t.me/lvivgromada',           'Львів Громада'),
    ('https://t.me/poltava_online24',      'Полтава Online'),
    ('https://t.me/mykolaiv_ukr',          'Миколаїв UA'),
    # --- Офіційні ЗСУ ---
    ('https://t.me/GeneralStaff_ua',       'Генштаб ЗСУ'),
    ('https://t.me/DPSUkraine',            'ДПСУ'),
    # --- Аналітика / обидві сторони ---
    ('https://t.me/rybar',                 'Rybar (RU)'),
    ('https://t.me/grey_zone',             'Серая Зона (RU)'),
    ('https://t.me/boris_rozhin',          'Colonelcassad (RU)'),
    ('https://t.me/intelslava',            'Intel Slava Z'),
    ('https://t.me/ua_sternenko',          'Стерненко'),
    ('https://t.me/flash_monitor',         'Flash Monitor'),
]


def seed_from_file(filepath: str) -> int:
    """Завантажує канали з data/my_channels.json (output export_channels.py)"""
    if not os.path.exists(filepath):
        return -1

    with open(filepath, encoding='utf-8') as f:
        channels = json.load(f)

    added = 0
    skipped = 0
    for ch in channels:
        url = ch.get('url', '').strip()
        if not url:
            skipped += 1
            continue
        tid = abs(ch.get('id', hash(url))) % 100_000_000
        _, created = Channel.get_or_create(
            telegram_id=tid,
            defaults={'name': ch.get('name', url), 'url': url, 'active': True}
        )
        if created:
            added += 1
            print(f"  + {ch.get('name', url)}")
        else:
            skipped += 1

    return added


def seed_defaults() -> int:
    """Завантажує вбудований список популярних каналів"""
    added = 0
    for url, name in DEFAULT_CHANNELS:
        tid = abs(hash(url)) % 100_000_000
        _, created = Channel.get_or_create(
            telegram_id=tid,
            defaults={'name': name, 'url': url, 'active': True}
        )
        if created:
            added += 1
            print(f"  + {name}  ({url})")

    return added


if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("  WarMap — Channel Seeder")
    print("=" * 50)

    my_channels_file = os.path.join(BASE_DIR, 'data', 'my_channels.json')

    if os.path.exists(my_channels_file):
        print(f"\nНайдено: data/my_channels.json")
        print("Імпортую твої канали...\n")
        added = seed_from_file(my_channels_file)
        print(f"\nДодано: {added} каналів з твого експорту.")
    else:
        print("\ndata/my_channels.json не знайдено.")
        print("Завантажую дефолтні канали моніторингу...\n")
        added = seed_defaults()
        print(f"\nДодано: {added} каналів.")
        print("\n  Щоб імпортувати СВОЇ канали:")
        print("  1. Відкрий CMD (не VS Code!)")
        print("  2. Запусти: python export_channels.py")
        print("  3. Введи 5-значний код з Telegram")
        print("  4. Знову запусти: python seed_channels.py")

    total = Channel.select().count()
    print(f"\nВсього каналів у БД: {total}")
    print("=" * 50)
