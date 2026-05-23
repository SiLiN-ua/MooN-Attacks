from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO
import threading
import json
import csv
import io
import os
from datetime import datetime
from dotenv import load_dotenv
from core.db import init_db, Event, Channel
from core.telegram_monitor import run_monitor
from core.trajectory import build_trajectories
from core.reporter import generate_report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(BASE_DIR, 'exports')

load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'moon_attacks_secret'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

monitor_thread = None

# Ensure exports dir and media dir exist
os.makedirs(EXPORTS_DIR, exist_ok=True)
MEDIA_DIR = os.path.join(BASE_DIR, 'static', 'media')
os.makedirs(MEDIA_DIR, exist_ok=True)

# ===== ГОЛОВНА =====
@app.route('/')
def splash():
    return render_template('splash.html')

@app.route('/map')
def index():
    return render_template('index.html')

@app.route('/feed')
def feed_page():
    return render_template('feed.html')

# ===== ПОДІЇ =====
@app.route('/api/events')
def get_events():
    limit = int(request.args.get('limit', 500))
    event_type = request.args.get('type', None)
    city = request.args.get('city', None)
    date_from = request.args.get('from', None)
    date_to = request.args.get('to', None)

    query = Event.select().order_by(Event.timestamp.desc())

    if event_type and event_type != 'all':
        query = query.where(Event.event_type == event_type)
    if city:
        query = query.where(Event.city.contains(city))
    if date_from:
        query = query.where(Event.timestamp >= date_from)
    if date_to:
        query = query.where(Event.timestamp <= date_to)

    events = []
    for e in query.limit(limit):
        events.append({
            'id': e.id,
            'timestamp': e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'text': e.text,
            'channel_name': e.channel_name,
            'channel_url': e.channel_url,
            'city': e.city,
            'lat': e.lat,
            'lon': e.lon,
            'event_type': e.event_type,
            'media_url': e.media_url,
            'message_id': e.message_id,
        })
    return jsonify(events)

# ===== СТОРІНКА КАНАЛУ =====
@app.route('/channel/<username>')
def channel_page(username):
    events = list(
        Event.select()
        .where(Event.channel_url.contains(username))
        .order_by(Event.timestamp.desc())
        .limit(300)
    )
    channel_url = f"https://t.me/{username}"
    channel_name = events[0].channel_name if events else username
    return render_template('channel.html',
                           username=username,
                           channel_url=channel_url,
                           channel_name=channel_name,
                           events=events)

# ===== НОВІ ПОДІЇ (POLLING) =====
@app.route('/api/events/new')
def get_new_events():
    since_id = int(request.args.get('since', 0))
    query = Event.select().where(Event.id > since_id).order_by(Event.id.asc()).limit(50)
    events = []
    for e in query:
        events.append({
            'id': e.id,
            'timestamp': e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'text': e.text,
            'channel_name': e.channel_name,
            'channel_url': e.channel_url,
            'city': e.city,
            'lat': e.lat,
            'lon': e.lon,
            'event_type': e.event_type,
            'media_url': e.media_url,
            'message_id': e.message_id,
        })
    return jsonify(events)

# ===== ТРАЄКТОРІЇ =====
@app.route('/api/trajectories')
def get_trajectories():
    date_from = request.args.get('from', None)
    date_to = request.args.get('to', None)

    query = Event.select().order_by(Event.timestamp.asc())
    if date_from:
        query = query.where(Event.timestamp >= date_from)
    if date_to:
        query = query.where(Event.timestamp <= date_to)

    events = []
    for e in query:
        if e.lat and e.lon:
            events.append({
                'id': e.id,
                'timestamp': e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'text': e.text[:300],
                'channel_name': e.channel_name,
                'channel_url': e.channel_url,
                'city': e.city,
                'lat': e.lat,
                'lon': e.lon,
                'event_type': e.event_type,
            })

    trajectories = build_trajectories(events)
    return jsonify(trajectories)

# ===== КАНАЛИ =====
@app.route('/api/channels', methods=['GET'])
def get_channels():
    channels = list(Channel.select().dicts())
    return jsonify(channels)

@app.route('/api/channels', methods=['POST'])
def add_channel():
    data = request.json
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()
    if not url:
        return jsonify({'status': 'error', 'message': 'URL required'}), 400
    channel, created = Channel.get_or_create(
        telegram_id=abs(hash(url)) % 100000000,
        defaults={'name': name or url, 'url': url}
    )
    return jsonify({'status': 'ok', 'created': created})

@app.route('/api/channels/<int:cid>', methods=['DELETE'])
def delete_channel(cid):
    Channel.delete().where(Channel.id == cid).execute()
    return jsonify({'status': 'ok'})

# ===== МОНІТОР =====
@app.route('/api/monitor/start', methods=['POST'])
def start_monitor():
    global monitor_thread
    channels = [c.url for c in Channel.select().where(Channel.active == True)]
    if not channels:
        return jsonify({'status': 'error', 'message': 'No channels added'}), 400
    if monitor_thread and monitor_thread.is_alive():
        return jsonify({'status': 'already_running'})
    monitor_thread = threading.Thread(
        target=run_monitor, args=(channels, socketio), daemon=True
    )
    monitor_thread.start()
    return jsonify({'status': 'ok', 'channels': len(channels)})

@app.route('/api/monitor/status')
def monitor_status():
    running = monitor_thread is not None and monitor_thread.is_alive()
    return jsonify({'running': running})

# ===== ЗАВАНТАЖЕННЯ ІСТОРІЇ З TELEGRAM =====

# Глобальний стан завантаження (замість SocketIO — надійніший polling)
history_state = {
    'running':  False,
    'channel':  '',
    'current':  0,
    'total':    0,
    'saved':    0,
    'done':     False,
    'error':    '',
}

@app.route('/api/history/load', methods=['POST'])
def api_history_load():
    global history_state
    data      = request.json or {}
    date_from = data.get('from')
    date_to   = data.get('to')
    cities    = data.get('cities', [])

    if not date_from or not date_to:
        return jsonify({'status': 'error', 'message': 'Вкажи діапазон дат'})

    all_channels = list(Channel.select().where(Channel.active == True))
    if not all_channels:
        return jsonify({'status': 'error', 'message': 'Немає каналів у списку'})

    channels = [ch.url for ch in all_channels]

    # Скидаємо стан
    history_state.update({'running': True, 'done': False, 'saved': 0,
                          'current': 0, 'total': len(channels), 'channel': '', 'error': ''})

    from core.telegram_monitor import run_load_history

    def _run():
        global history_state
        try:
            run_load_history(channels, date_from, date_to,
                             cities if cities else None, None,
                             progress_cb=lambda ch, cur, tot, saved: history_state.update(
                                 {'channel': ch, 'current': cur, 'total': tot, 'saved': saved}
                             ))
        except Exception as e:
            history_state['error'] = str(e)
        finally:
            history_state['running'] = False
            history_state['done']    = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({'status': 'ok', 'channels': len(channels)})


@app.route('/api/history/status')
def api_history_status():
    return jsonify(history_state)

# ===== МАРШРУТ =====
@app.route('/api/route/channels', methods=['POST'])
def get_route_channels():
    """Знаходить канали в БД чия НАЗВА містить міста маршруту"""
    cities = request.json.get('cities', [])
    if not cities:
        return jsonify([])
    matched = []
    for ch in Channel.select().where(Channel.active == True):
        name_lower = ch.name.lower()
        for city in cities:
            if city.lower() in name_lower:
                matched.append({'id': ch.id, 'name': ch.name, 'url': ch.url})
                break
    return jsonify(matched)

@app.route('/api/route/events', methods=['POST'])
def get_route_events():
    """Події для міст маршруту — шукає по тексту, місту події і назві каналу"""
    cities = request.json.get('cities', [])
    date_from = request.json.get('from', None)
    date_to = request.json.get('to', None)

    if not cities:
        return jsonify([])

    query = Event.select().order_by(Event.timestamp.desc())
    if date_from:
        query = query.where(Event.timestamp >= date_from)
    if date_to:
        query = query.where(Event.timestamp <= date_to)

    events = []
    for e in query.limit(2000):
        city_lower  = (e.city or '').lower()
        ch_lower    = (e.channel_name or '').lower()
        text_lower  = (e.text or '').lower()
        for c in cities:
            cl = c.lower()
            if (cl in city_lower or cl in ch_lower or cl in text_lower):
                events.append({
                    'id': e.id,
                    'timestamp': e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'text': e.text,
                    'channel_name': e.channel_name,
                    'channel_url': e.channel_url,
                    'city': e.city,
                    'lat': e.lat,
                    'lon': e.lon,
                    'event_type': e.event_type,
                    'media_url': e.media_url,
                    'message_id': e.message_id,
                })
                break
    return jsonify(events)

# ===== AI РЕПОРТ =====
@app.route('/api/report', methods=['POST'])
def api_report():
    data = request.json or {}
    date_from  = data.get('from')
    date_to    = data.get('to')
    route      = data.get('route', [])
    event_ids  = data.get('event_ids', [])   # конкретні ID якщо є

    query = Event.select().order_by(Event.timestamp.desc())
    if event_ids:
        query = query.where(Event.id.in_(event_ids))
    else:
        if date_from: query = query.where(Event.timestamp >= date_from)
        if date_to:   query = query.where(Event.timestamp <= date_to)

    events = []
    for e in query.limit(2500):
        events.append({
            'id':           e.id,
            'timestamp':    e.timestamp.strftime('%Y-%m-%d %H:%M'),
            'text':         e.text,
            'channel_name': e.channel_name,
            'channel_url':  e.channel_url,
            'city':         e.city,
            'lat':          e.lat,
            'lon':          e.lon,
            'event_type':   e.event_type,
            'media_url':    e.media_url,
            'message_id':   e.message_id,
        })

    html_content = generate_report(events, route)

    # ── Фільтри для міні-карти ──────────────────────────────────────────────

    def _is_rf_territory(lat, lon):
        """Тільки РФ-територія і окуповані райони (без вільної України)."""
        if lat is None or lon is None:
            return False
        if lon >= 36.5:          # Донбас, Кубань, вся РФ схід від лінії фронту
            return True
        if lat <= 46.5 and lon >= 32.0:   # Крим + окуповане південне узбережжя
            return True
        return False

    def _city_in_text(event):
        """Місто має реально згадуватися в тексті повідомлення."""
        if not (event['lat'] and event['lon'] and event['city']):
            return False
        city_low   = event['city'].lower()
        text_low   = (event['text'] or '').lower()
        city_parts = [p for p in city_low.split() if len(p) >= 4]
        if not city_parts:
            return True   # дуже коротка назва — довіряємо
        return any(part in text_low for part in city_parts)

    map_events = [{'lat': e['lat'], 'lon': e['lon'],
                   'event_type': e['event_type'], 'city': e['city'],
                   'timestamp': e['timestamp'], 'text': e['text'][:120]}
                  for e in events
                  if _city_in_text(e) and _is_rf_territory(e['lat'], e['lon'])]

    # Центр подій для NASA FIRMS
    firms_url = None
    if map_events:
        center_lat = sum(e['lat'] for e in map_events) / len(map_events)
        center_lon = sum(e['lon'] for e in map_events) / len(map_events)
        # Дата початку у форматі YYYY-MM-DD для FIRMS
        try:
            date_str = events[-1]['timestamp'][:10]  # найстаріша подія
            date_end = events[0]['timestamp'][:10]   # найновіша
            firms_date = f"{date_str}..{date_end}" if date_str != date_end else date_str
        except Exception:
            firms_date = "24hrs"
        firms_url = (f"https://firms.modaps.eosdis.nasa.gov/map/"
                     f"#d:{firms_date};@{center_lon:.4f},{center_lat:.4f},11z")

    return jsonify({'html': html_content, 'events_count': len(events),
                    'map_events': map_events, 'firms_url': firms_url})

@app.route('/report')
def report_page():
    return render_template('report.html')

# ===== ОЧИСТКА ПОДІЙ =====
@app.route('/api/events/clear', methods=['DELETE'])
def clear_events():
    count = Event.delete().execute()
    return jsonify({'status': 'ok', 'deleted': count})

# ===== ЕКСПОРТ =====
@app.route('/api/export/json', methods=['POST'])
def export_json():
    data = request.json or {}
    date_from = data.get('from')
    date_to = data.get('to')

    query = Event.select().order_by(Event.timestamp.desc())
    if date_from:
        query = query.where(Event.timestamp >= date_from)
    if date_to:
        query = query.where(Event.timestamp <= date_to)

    events = []
    for e in query:
        events.append({
            'id': e.id,
            'timestamp': e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'text': e.text,
            'channel_name': e.channel_name,
            'channel_url': e.channel_url,
            'city': e.city,
            'lat': e.lat,
            'lon': e.lon,
            'event_type': e.event_type,
        })

    filename = f"moon_attacks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(EXPORTS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    return send_file(filepath, as_attachment=True)

@app.route('/api/export/csv', methods=['POST'])
def export_csv():
    data = request.json or {}
    date_from = data.get('from')
    date_to = data.get('to')

    query = Event.select().order_by(Event.timestamp.desc())
    if date_from:
        query = query.where(Event.timestamp >= date_from)
    if date_to:
        query = query.where(Event.timestamp <= date_to)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Time', 'City', 'Type', 'Channel', 'Text', 'URL'])
    for e in query:
        writer.writerow([
            e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            e.city or '', e.event_type,
            e.channel_name, e.text[:300], e.channel_url
        ])
    output.seek(0)
    filename = f"moon_attacks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(EXPORTS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        f.write(output.getvalue())
    return send_file(filepath, as_attachment=True)

@app.route('/api/export/html', methods=['POST'])
def export_html():
    data = request.json or {}
    date_from = data.get('from')
    date_to = data.get('to')

    query = Event.select().order_by(Event.timestamp.desc())
    if date_from:
        query = query.where(Event.timestamp >= date_from)
    if date_to:
        query = query.where(Event.timestamp <= date_to)

    rows = ''
    for e in query:
        rows += f"""
        <tr>
            <td>{e.timestamp.strftime('%Y-%m-%d %H:%M')}</td>
            <td>{e.city or ''}</td>
            <td>{e.event_type}</td>
            <td><a href="{e.channel_url}" target="_blank">{e.channel_name}</a></td>
            <td>{e.text[:200]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>MooN Attacks Report</title>
    <style>
        body{{font-family:monospace;background:#0a0c10;color:#e0e0e0;padding:20px}}
        h1{{color:#00b4ff}} table{{width:100%;border-collapse:collapse;margin-top:20px}}
        th{{background:#141920;color:#00b4ff;padding:10px;text-align:left}}
        td{{padding:8px;border-bottom:1px solid #1e2730;font-size:0.85rem}}
        a{{color:#a855f7}} tr:hover{{background:#141920}}
    </style></head><body>
    <h1>🌙 MooN Attacks Report</h1>
    <p style="color:#555">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <table><thead><tr><th>Time</th><th>City</th><th>Type</th><th>Channel</th><th>Text</th></tr></thead>
    <tbody>{rows}</tbody></table></body></html>"""

    filename = f"moon_attacks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(EXPORTS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    return send_file(filepath, as_attachment=True)

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, port=5001, host='0.0.0.0')
