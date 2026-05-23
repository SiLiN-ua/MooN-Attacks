import os
import anthropic
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

EVENT_PRIORITY = {'missile': 0, 'explosion': 1, 'drone': 2,
                  'shot_down': 3, 'flyover': 4, 'unknown': 5}

MAX_EVENTS   = 300
MAX_TEXT_LEN = 220


def select_top_events(events, max_n):
    sorted_ev = sorted(events,
                       key=lambda e: EVENT_PRIORITY.get(e.get('event_type', 'unknown'), 5))
    return sorted_ev[:max_n]


def format_events(events):
    lines = []
    for i, e in enumerate(events):
        text = (e.get('text') or '')[:MAX_TEXT_LEN].replace('\n', ' ')
        slug = (e.get('channel_url') or '').replace('https://t.me/', '').strip('/')
        msg_id = e.get('message_id') or ''
        tg_link = f'https://t.me/{slug}/{msg_id}' if slug and msg_id else (e.get('channel_url') or '')
        media = e.get('media_url') or ''
        lines.append(
            f"[#{i+1}] [{e['timestamp']}] [{e['event_type'].upper()}] "
            f"Город:{e.get('city') or '—'} | "
            f"Канал:{e['channel_name']} | "
            f"TG:{tg_link} | "
            f"ФОТО:{media or 'нет'} | "
            f"Текст:{text}"
        )
    return '\n'.join(lines)


def generate_report(events: list, route: list = None) -> str:
    if not events:
        return '<p>Нет данных для отчёта.</p>'

    total        = len(events)
    route_str    = ' → '.join(route) if route else 'не задан'
    top_events   = select_top_events(events, MAX_EVENTS)
    events_str   = format_events(top_events)
    period_from  = events[-1]['timestamp'] if events else '—'
    period_to    = events[0]['timestamp']  if events else '—'
    note = (f'показаны {len(top_events)} из {total} — приоритет: ракеты/взрывы/дроны'
            if total > MAX_EVENTS else f'всего {total}')

    prompt = f"""Ты — профессиональный военный аналитик разведки. Составь подробный HTML-отчёт.

МАРШРУТ: {route_str}
ПЕРИОД: {period_from} — {period_to}
СОБЫТИЯ ({note}):
{events_str}

═══════════════════════════════════════
СТРУКТУРА ОТЧЁТА (строго HTML, без markdown, без ```, без <html><head><body>):
═══════════════════════════════════════

<h2>1. РЕЗЮМЕ</h2>
3-4 предложения — главное за период, масштаб, результат.

<h2>2. СТАТИСТИКА</h2>
<ul> взрывы / дроны / ракеты / сбитые / пролёты / пожары / пострадавшие — с конкретными числами </ul>

<h2>3. ХРОНОЛОГИЯ СОБЫТИЙ</h2>
⚠️ ЭТО САМЫЙ ВАЖНЫЙ РАЗДЕЛ. Включи как можно больше событий из списка выше.
Цель — 60–70 строк (не больше 70, иначе не хватит места на остальные разделы).
Каждое упоминание взрыва, дрона, ракеты, сбития, пожара — отдельная строка.
НЕ ПРОПУСКАЙ события — выбирай самые значимые из всего списка.

Оформи ТАБЛИЦЕЙ:
<table class="chrono-table">
<thead><tr>
  <th>Сообщение из Telegram</th>
  <th>Военный анализ</th>
  <th>Источник</th>
</tr></thead>
<tbody>
<!-- Для КАЖДОГО события из списка: -->
<tr>
  <td>
    <div class="tg-bubble">
      <!-- ОБЯЗАТЕЛЬНО: если ФОТО не 'нет' — вставь img: -->
      <!-- <img src="ЗНАЧЕНИЕ_ПОЛЯ_ФОТО" class="tg-photo"> -->
      <div class="tg-text">текст сообщения до 180 символов</div>
      <div class="tg-meta">📡 Название канала · ЧЧ:ММ дд.мм</div>
    </div>
  </td>
  <td class="chrono-analysis">1-2 предложения: что произошло, военное значение</td>
  <td class="chrono-src"><a href="ЗНАЧЕНИЕ_ПОЛЯ_TG" target="_blank">🔗 Telegram</a></td>
</tr>
</tbody>
</table>

Используй реальные данные из событий (#1, #2...) — поля TG: и ФОТО: содержат готовые ссылки.

<h2>4. АНАЛИЗ ПО ТИПАМ</h2>
⚠️ К КАЖДОМУ факту добавляй ссылку-источник из поля TG: события!
Формат: "факт (<a href="TG-ССЫЛКА" target="_blank">📡 Канал · ЧЧ:ММ</a>)"

<h3>💥 Взрывы и прилёты</h3>
<p>Подробно — волны, время, места, масштаб. Каждый прилёт — со ссылкой на TG-источник.</p>
<h3>🚁 БПЛА</h3>
<p>Тактика, направления, количество, цели — со ссылками на источники.</p>
<h3>🚀 Ракеты</h3>
<p>Если были — тип, количество, траектория — со ссылками.</p>
<h3>🛡️ ПВО</h3>
<p>Что сработало, что нет, где прорыв — со ссылками на каналы ПВО.</p>

<h2>5. МАРШРУТ АТАКИ</h2>
Откуда → куда летели. Маршрут мониторинга: {route_str}
Восстанови по хронологии сообщений если маршрут не указан.
Укажи координаты ключевых точек поражения если известны.

<h2>6. ОТКРЫТЫЕ ИСТОЧНИКИ И РЕАКЦИИ</h2>
Выполни веб-поиск:
1. Атака на [город из маршрута] {period_from[:10]} новости
2. МО России заявление {period_from[:10]}
3. Украина ВСУ атака {period_from[:10]} заявление
4. Ответный удар Россия {period_from[:10]}
5. NASA FIRMS пожар {period_from[:10]} координаты

<h3>📰 Медиа и OSINT</h3>
Минимум 5-7 ссылок с цитатами из источников.
<a href="URL" target="_blank">Название источника</a> — цитата или описание.

<h3>🔥 NASA FIRMS — тепловые аномалии</h3>
Найди данные NASA FIRMS о тепловых аномалиях в районе атаки.
Вставь прямую ссылку на карту FIRMS для этого района и даты:
<a href="https://firms.modaps.eosdis.nasa.gov/map/#d:ДАТА;@ДОЛ,ШИР,12z" target="_blank">🔥 Открыть карту пожаров NASA FIRMS</a>
Если нашёл конкретные координаты пожара — укажи их.

<h3>🇷🇺 Реакция РФ</h3>
Официальные заявления МО, Кремля, губернаторов, оперштабов.
К КАЖДОЙ цитате — ссылка на источник:
<p>"Цитата официального лица" — <a href="URL" target="_blank">📰 Источник, дата</a></p>

<h3>🇺🇦 Позиция Украины</h3>
Заявления ВСУ, ОП, Зеленского, Генштаба.
К каждой цитате — ссылка:
<p>"Цитата" — <a href="URL" target="_blank">📰 Источник</a></p>

<h3>⚔️ Ответный удар</h3>
Заявления об ударах возмездия — что и где ударили в ответ.
<p>Описание удара — <a href="URL" target="_blank">📰 Источник</a></p>

<h3>🌍 Международная реакция</h3>
США, НАТО, санкции, комментарии — с цитатами и ссылками.

<h2>7. ИТОГОВАЯ ОЦЕНКА</h2>
2-3 абзаца — военное и стратегическое значение, долгосрочные последствия.

═══════════════════════════════════════
ПРАВИЛА:
- Только чистый HTML, без ```html, без <html><head><body>
- Разрешённые теги: <h2> <h3> <p> <ul> <li> <strong> <em> <table> <tr> <td> <th> <a> <img> <div> <span>
- Span для типов: <span class="explosion">💥</span> <span class="drone">🚁</span> <span class="missile">🚀</span>
- Язык: русский, военный стиль
- ХРОНОЛОГИЯ — самый важный раздел, не экономь строки!
- СЕКЦИИ 4 и 6: обязательно ссылки на источник для каждого факта и каждой цитаты!
"""

    tools    = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]
    messages = [{'role': 'user', 'content': prompt}]

    # Пробуем сначала 16 000 токенов, если модель не поддерживает — снижаем до 8 000
    for max_tok in (16000, 8000):
        try:
            result = _run_report_loop(client, messages, tools, max_tok)
            if result is not None:
                return result
            # None означает loop завершился без end_turn — пробуем fallback
            break
        except anthropic.BadRequestError as e:
            err_str = str(e)
            if 'max_tokens' in err_str and str(max_tok) in err_str:
                # Лимит токенов модели превышен — повторяем с меньшим значением
                print(f'[REPORT] max_tokens={max_tok} слишком велик, повторяю с меньшим...')
                messages = [{'role': 'user', 'content': prompt}]   # сбрасываем диалог
                continue
            # Другая BadRequestError (промпт слишком большой и т.п.) → fallback
            print(f'[REPORT] BadRequestError: {e}')
            return _fallback(events[:50], route_str, period_from, period_to, total)
        except Exception as e:
            print(f'[REPORT] Error: {e}')
            return f'<p style="color:#ff4444">Ошибка генерации: {e}</p>'

    return _fallback(events[:50], route_str, period_from, period_to, total)


def _run_report_loop(client, messages, tools, max_tokens):
    """Выполняет agentic loop генерации отчёта. Возвращает HTML-строку или None."""
    msgs = list(messages)   # копия чтобы не мутировать оригинал
    for _ in range(15):
        response = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=max_tokens,
            tools=tools,
            messages=msgs,
        )

        if response.stop_reason == 'end_turn':
            parts = [b.text for b in response.content if hasattr(b, 'text')]
            return '\n'.join(parts).strip() or '<p>Пустой отчёт.</p>'

        if response.stop_reason == 'tool_use':
            msgs.append({'role': 'assistant', 'content': response.content})
            tool_results = []
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': '',
                    })
            if tool_results:
                msgs.append({'role': 'user', 'content': tool_results})
            continue

        print(f'[REPORT] stop_reason={response.stop_reason}')
        break
    return None


def _fallback(events, route_str, period_from, period_to, total):
    """Запасной — без веб-поиска, топ-50"""
    events_str = format_events(events)
    prompt = f"""Военный аналитик. Кратко проанализируй {len(events)} из {total} событий.
Маршрут: {route_str}. Период: {period_from}–{period_to}.
{events_str}
HTML: резюме, статистика, хронология таблицей, итог. Без <html><head><body>."""
    try:
        r = client.messages.create(
            model='claude-opus-4-5', max_tokens=4000,
            messages=[{'role': 'user', 'content': prompt}])
        parts = [b.text for b in r.content if hasattr(b, 'text')]
        return '\n'.join(parts).strip() or '<p>Пустой отчёт.</p>'
    except Exception as e:
        return f'<p style="color:#ff4444">Ошибка: {e}</p>'
