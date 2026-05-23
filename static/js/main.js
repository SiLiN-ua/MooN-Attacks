// ===== КАРТА =====
const map = L.map('map', {
    zoomControl: true,
    minZoom: 2,
}).setView([48.0, 32.0], 4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© CartoDB', maxZoom: 18
}).addTo(map);

const TYPE_COLORS = {
    explosion: '#ff4444', drone: '#ff9900', missile: '#cc44ff',
    shot_down: '#00ff88', flyover: '#ffdd00', unknown: '#7a8a99',
};
const TYPE_ICONS = {
    explosion: '💥', drone: '🚁', missile: '🚀',
    shot_down: '🛡️', flyover: '👁️', unknown: '❓'
};
const TRAJ_COLORS = {
    drone: '#ff9900', missile: '#cc44ff', flyover: '#ffdd00'
};

let allEvents = [];
let markers = {};
let trajectoryLayers = [];
let routeLayer = null;
let currentFilter = 'all';
let currentCity = '';
let currentMode = 'live';
let currentTab = 'feed';
let monitorRunning = false;
let sessionActive = false;   // true тільки якщо Start натиснутий У ЦІЙ сесії

// ===== SOCKET.IO =====
const socket = io();
socket.on('new_event', (event) => {
    if (currentMode !== 'live') return;
    if (!sessionActive) return;   // ← не показуємо якщо Start не натиснутий
    allEvents.unshift(event);
    addMarker(event);
    addEventCard(event, true);
    addFullPost(event, true);
    updateStats();
});

// ===== РЕЖИМ =====
function setMode(mode) {
    currentMode = mode;
    document.getElementById('btn-live').classList.toggle('active', mode === 'live');
    document.getElementById('btn-history').classList.toggle('active', mode === 'history');
    document.getElementById('history-bar').classList.toggle('hidden', mode === 'live');
    if (mode === 'live') loadLive();
}

// ===== ФІЛЬТР: ТІЛЬКИ РФ-ТЕРИТОРІЯ =====
function isRFTerritory(lat, lon) {
    if (!lat || !lon) return false;
    // Россия, оккупированный Донбас (восточнее линии фронта ~36.5°)
    if (lon >= 36.5) return true;
    // Крым и оккупированное южное побережье
    if (lat <= 46.5 && lon >= 32.0) return true;
    return false;
}

// ===== МАРКЕРИ =====
function addMarker(event) {
    if (!event.lat || !event.lon) return;
    // Показываем точки только на территории РФ и оккупированных районов
    if (!isRFTerritory(event.lat, event.lon)) return;
    const color = TYPE_COLORS[event.event_type] || TYPE_COLORS.unknown;
    const marker = L.circleMarker([event.lat, event.lon], {
        radius: event.event_type === 'explosion' ? 11 : 8,
        fillColor: color, color: color, weight: 2, opacity: 0.95, fillOpacity: 0.75,
    });
    const slug = event.channel_url.replace('https://t.me/', '').replace(/\//g, '');
    const tgLink = event.message_id
        ? `https://t.me/${slug}/${event.message_id}`
        : event.channel_url;
    const photoHtml = event.media_url && event.media_url.startsWith('/static/')
        ? `<img src="${event.media_url}" class="popup-photo" onclick="window.open('${event.media_url}','_blank')">`
        : '';
    marker.bindPopup(`
        <div class="popup-title">${TYPE_ICONS[event.event_type] || '❓'} ${event.event_type.toUpperCase()} — ${event.city || 'Unknown'}</div>
        <div class="popup-text">${event.text}</div>
        ${photoHtml}
        <div class="popup-channel">📡 <a href="${event.channel_url}" target="_blank">${event.channel_name}</a></div>
        <div class="popup-time">🕐 ${event.timestamp}</div>
        <div class="popup-tglink"><a href="${tgLink}" target="_blank">🔗 Open in Telegram</a></div>
    `, { maxWidth: 320 });
    marker.addTo(map);
    markers[event.id] = marker;
}

function clearMarkers() {
    Object.values(markers).forEach(m => map.removeLayer(m));
    markers = {};
}

// ===== ТРАЄКТОРІЇ =====
function drawTrajectories(trajectories) {
    trajectoryLayers.forEach(l => map.removeLayer(l));
    trajectoryLayers = [];

    trajectories.forEach(traj => {
        if (traj.points.length < 2) return;
        const color = TRAJ_COLORS[traj.type] || '#ffffff';

        // Лінія
        const line = L.polyline(traj.points, {
            color: color, weight: 2.5, opacity: 0.8,
            dashArray: '8, 6',
        });

        // Стрілки по лінії
        traj.points.forEach((pt, i) => {
            if (i === 0) {
                // Початок — маленький кружок
                const start = L.circleMarker(pt, {
                    radius: 5, fillColor: color, color: '#fff',
                    weight: 1, fillOpacity: 1
                });
                start.addTo(map);
                trajectoryLayers.push(start);
            }
            if (i === traj.points.length - 1) {
                // Кінець — більший маркер
                const end = L.circleMarker(pt, {
                    radius: 8, fillColor: color, color: '#fff',
                    weight: 2, fillOpacity: 0.9
                });
                const ev = traj.events[i];
                end.bindPopup(`
                    <div class="popup-title">🎯 END POINT — ${traj.cities[i] || 'Unknown'}</div>
                    <div class="popup-text">${ev.text}</div>
                    <div class="popup-channel">📡 <a href="${ev.channel_url}" target="_blank">${ev.channel_name}</a></div>
                    <div class="popup-time">🕐 ${ev.timestamp}</div>
                `);
                end.addTo(map);
                trajectoryLayers.push(end);
            }
        });

        // Попап на лінії
        line.bindPopup(`
            <div class="popup-title">〰️ TRAJECTORY — ${traj.type.toUpperCase()}</div>
            <div class="popup-text">Route: ${traj.cities.filter(Boolean).join(' → ')}</div>
            <div class="popup-time">${traj.events.length} confirmed points</div>
        `);

        line.addTo(map);
        trajectoryLayers.push(line);
    });
}

// ===== СТРІЧКА ПОДІЙ =====
function addEventCard(event, prepend = false) {
    if (!matchesFilter(event)) return;
    const feed = document.getElementById('tab-feed');
    const card = document.createElement('div');
    card.className = `event-card ${event.event_type}`;
    card.innerHTML = `
        <div class="event-top">
            <span class="event-type ${event.event_type}">${TYPE_ICONS[event.event_type] || '❓'} ${event.event_type}</span>
            <span class="event-time">${event.timestamp.slice(11, 16)}</span>
        </div>
        ${event.city ? `<div class="event-city">📍 ${event.city}</div>` : ''}
        <div class="event-text">${event.text.slice(0, 120)}</div>
        <div class="event-channel">📡 <a href="${event.channel_url}" target="_blank" onclick="event.stopPropagation()">${event.channel_name}</a></div>
    `;
    card.onclick = () => {
        if (event.lat && event.lon) {
            map.setView([event.lat, event.lon], 10);
            if (markers[event.id]) markers[event.id].openPopup();
        }
    };
    prepend && feed.firstChild ? feed.insertBefore(card, feed.firstChild) : feed.appendChild(card);
    document.getElementById('events-count').textContent = `${allEvents.length} events`;
}

// ===== ПОВНІ ПОСТИ =====
function addFullPost(event, prepend = false) {
    if (!matchesFilter(event)) return;
    const panel = document.getElementById('tab-full');
    const post = document.createElement('div');
    post.className = `full-post ${event.event_type}`;
    const slug = event.channel_url.replace('https://t.me/', '').replace(/\//g, '');
    const tgMsgLink = event.message_id
        ? `https://t.me/${slug}/${event.message_id}`
        : event.channel_url;
    const mediaHtml = event.media_url
        ? (event.media_url.startsWith('/static/')
            ? `<img src="${event.media_url}" class="fp-photo" onclick="window.open('${event.media_url}','_blank');event.stopPropagation()">`
            : `<a href="${event.media_url}" target="_blank" onclick="event.stopPropagation()" class="fp-media-link">📎 Media / Video</a>`)
        : '';
    post.innerHTML = `
        <div class="fp-header">
            <span class="fp-type ${event.event_type}">${TYPE_ICONS[event.event_type] || '❓'} ${event.event_type.toUpperCase()}</span>
            <div class="fp-meta">
                ${event.city ? `<span class="fp-city">📍 ${event.city}</span>` : ''}
                <span class="fp-time">🕐 ${event.timestamp}</span>
                <a href="/channel/${slug}" target="_blank" class="fp-open" onclick="event.stopPropagation()" title="Open channel page">↗</a>
            </div>
        </div>
        <div class="fp-text">${event.text}</div>
        ${mediaHtml}
        <div class="fp-channel">
            📡 <a href="${event.channel_url}" target="_blank" onclick="event.stopPropagation()">${event.channel_name}</a>
            &nbsp;·&nbsp; <a href="${tgMsgLink}" target="_blank" onclick="event.stopPropagation()" class="fp-tglink">🔗 Telegram</a>
        </div>
    `;
    post.onclick = () => {
        if (event.lat && event.lon) {
            map.setView([event.lat, event.lon], 10);
            if (markers[event.id]) markers[event.id].openPopup();
        }
    };
    prepend && panel.firstChild ? panel.insertBefore(post, panel.firstChild) : panel.appendChild(post);
}

// ===== ПАНЕЛЬ =====
let panelState = 'normal'; // normal | expanded | collapsed
function togglePanel() {
    const panel = document.querySelector('.events-panel');
    const btn = document.getElementById('btn-panel-toggle');
    if (panelState === 'normal') {
        panel.classList.add('expanded');
        panelState = 'expanded';
        btn.textContent = '▼ Collapse';
    } else if (panelState === 'expanded') {
        panel.classList.remove('expanded');
        panel.classList.add('collapsed');
        panelState = 'collapsed';
        btn.textContent = '▲ Expand';
    } else {
        panel.classList.remove('collapsed');
        panelState = 'normal';
        btn.textContent = '▲ Expand';
    }
}

// ===== ТАБИ =====
function setTab(tab, btn) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-feed').classList.toggle('hidden', tab !== 'feed');
    document.getElementById('tab-full').classList.toggle('hidden', tab !== 'full');
}

// ===== ФІЛЬТРИ =====
function matchesFilter(event) {
    if (currentFilter !== 'all' && event.event_type !== currentFilter) return false;
    if (currentCity && !(event.city || '').toLowerCase().includes(currentCity)) return false;
    return true;
}

function filterEvents(type, btn) {
    currentFilter = type;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    // Обновляем активную кнопку в sidebar
    document.querySelectorAll(`.filter-btn[data-type="${type}"]`).forEach(b => b.classList.add('active'));
    reRender();
    // Прокручиваем вниз к ленте
    document.querySelector('.events-panel').scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function filterByCity(val) {
    currentCity = val.toLowerCase();
    reRender();
}

function reRender() {
    clearMarkers();
    document.getElementById('tab-feed').innerHTML = '';
    document.getElementById('tab-full').innerHTML = '';
    allEvents.forEach(e => {
        addMarker(e);
        addEventCard(e);
        addFullPost(e);
    });
    document.getElementById('events-count').textContent = `${allEvents.filter(matchesFilter).length} events`;
}

// ===== СТАТИСТИКА =====
function updateStats() {
    document.getElementById('h-total').textContent = allEvents.length;
    ['explosion', 'drone', 'missile', 'shot_down', 'flyover'].forEach(type => {
        document.getElementById(`h-${type}`).textContent =
            allEvents.filter(e => e.event_type === type).length;
    });
}

// ===== LIVE =====
async function loadLive() {
    clearMarkers();
    trajectoryLayers.forEach(l => map.removeLayer(l));
    trajectoryLayers = [];
    document.getElementById('tab-feed').innerHTML = '';
    document.getElementById('tab-full').innerHTML = '';

    // Стартуємо з порожньою картою — тільки встановлюємо lastEventId
    // щоб pollNewEvents підхопив нові події з цього моменту
    allEvents = [];
    const res = await fetch('/api/events?limit=1');
    const latest = await res.json();
    if (latest.length) lastEventId = latest[0].id;
    updateStats();
}

// ===== HISTORICAL =====
async function loadHistorical() {
    const from = document.getElementById('dt-from').value;
    const to = document.getElementById('dt-to').value;
    if (!from && !to) { alert('Select at least one date!'); return; }

    clearMarkers();
    document.getElementById('tab-feed').innerHTML = '';
    document.getElementById('tab-full').innerHTML = '';

    let url = `/api/events?limit=1000`;
    if (from) url += `&from=${from.replace('T', ' ')}`;
    if (to) url += `&to=${to.replace('T', ' ')}`;

    const res = await fetch(url);
    allEvents = await res.json();
    allEvents.forEach(e => { addMarker(e); addEventCard(e); addFullPost(e); });
    updateStats();
}

async function loadTrajectories() {
    const from = document.getElementById('dt-from').value;
    const to = document.getElementById('dt-to').value;

    let url = '/api/trajectories?';
    if (from) url += `from=${from.replace('T', ' ')}&`;
    if (to) url += `to=${to.replace('T', ' ')}`;

    const res = await fetch(url);
    const trajectories = await res.json();
    drawTrajectories(trajectories);
    alert(`Loaded ${trajectories.length} trajectories`);
}

// ===== МАРШРУТ =====
function addRouteCity() {
    const container = document.getElementById('route-cities');
    const row = document.createElement('div');
    row.className = 'route-city-row';
    row.innerHTML = `
        <input type="text" class="route-input" placeholder="City...">
        <button class="route-del" onclick="removeRouteCity(this)">×</button>
    `;
    container.appendChild(row);
}

function removeRouteCity(btn) {
    const rows = document.querySelectorAll('.route-city-row');
    if (rows.length > 1) btn.parentElement.remove();
}

async function searchRoute() {
    const cities = Array.from(document.querySelectorAll('.route-input'))
        .map(i => i.value.trim()).filter(v => v);
    if (!cities.length) { alert('Enter at least one city!'); return; }

    const from = document.getElementById('dt-from').value;
    const to = document.getElementById('dt-to').value;

    const res = await fetch('/api/route/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            cities,
            from: from ? from.replace('T', ' ') : null,
            to: to ? to.replace('T', ' ') : null,
        })
    });
    const events = await res.json();

    clearMarkers();
    document.getElementById('tab-feed').innerHTML = '';
    document.getElementById('tab-full').innerHTML = '';
    allEvents = events;
    events.forEach(e => { addMarker(e); addEventCard(e); addFullPost(e); });
    updateStats();

    // Малюємо маршрут на карті
    if (routeLayer) map.removeLayer(routeLayer);
    // Знаходимо унікальні міста в порядку
    const pts = events.filter(e => e.lat && e.lon).map(e => [e.lat, e.lon]);
    if (pts.length > 1) {
        routeLayer = L.polyline(pts, { color: '#00ff88', weight: 2, dashArray: '4,8', opacity: 0.6 });
        routeLayer.addTo(map);
    }
}

async function findRouteChannels() {
    const cities = Array.from(document.querySelectorAll('.route-input'))
        .map(i => i.value.trim()).filter(v => v);
    if (!cities.length) { alert('Enter at least one city!'); return; }

    const res = await fetch('/api/route/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cities })
    });
    const channels = await res.json();
    const box = document.getElementById('route-channels-result');

    if (!channels.length) {
        box.innerHTML = '<div style="color:#555;font-size:0.7rem;padding:4px 0">No channels found for these cities</div>';
        return;
    }

    box.innerHTML = `
        <div style="color:var(--shot_down);font-size:0.7rem;padding:4px 0;font-weight:bold">
            📡 ${channels.length} channels found:
        </div>
        ${channels.map(c => `
            <div class="route-ch-item">
                <span>${c.name}</span>
                <a href="${c.url}" target="_blank">↗</a>
            </div>
        `).join('')}
        <button class="btn-route-search" style="margin-top:6px" onclick="searchRouteByChannels(${JSON.stringify(channels.map(c=>c.name))})">
            🔍 Monitor these channels
        </button>
    `;
}

async function searchRouteByChannels(channelNames) {
    clearMarkers();
    document.getElementById('tab-feed').innerHTML = '';
    document.getElementById('tab-full').innerHTML = '';

    const res = await fetch('/api/route/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cities: channelNames })
    });
    const events = await res.json();
    allEvents = events;
    events.forEach(e => { addMarker(e); addEventCard(e); addFullPost(e); });
    updateStats();
}

function clearRoute() {
    document.querySelectorAll('.route-input').forEach((inp, i) => {
        if (i === 0) inp.value = '';
    });
    const rows = document.querySelectorAll('.route-city-row');
    rows.forEach((r, i) => { if (i > 0) r.remove(); });
    if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
    loadLive();
}

// ===== КАНАЛИ =====
async function loadChannels() {
    const res = await fetch('/api/channels');
    const channels = await res.json();
    const list = document.getElementById('channels-list');
    if (!channels.length) {
        list.innerHTML = '<div style="color:#555;font-size:0.72rem;padding:4px">No channels yet</div>';
        return;
    }
    list.innerHTML = channels.map(c => {
        const slug = c.url.replace('https://t.me/', '').replace(/\//g, '');
        return `
        <div class="channel-item">
            <span class="channel-name" title="${c.url}" onclick="window.open('/channel/${slug}','_blank')" style="cursor:pointer">${c.name || c.url}</span>
            <button class="channel-del" onclick="deleteChannel(${c.id})"><i class="fas fa-times"></i></button>
        </div>`;
    }).join('');
}

async function addChannel() {
    const url = document.getElementById('ch-url').value.trim();
    const name = document.getElementById('ch-name').value.trim();
    if (!url) { alert('Enter channel URL!'); return; }
    const res = await fetch('/api/channels', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, name })
    });
    const data = await res.json();
    if (data.status === 'ok') {
        document.getElementById('ch-url').value = '';
        document.getElementById('ch-name').value = '';
        loadChannels();
    }
}

async function deleteChannel(id) {
    await fetch(`/api/channels/${id}`, { method: 'DELETE' });
    loadChannels();
}

// ===== МОНІТОР =====
async function toggleMonitor() {
    if (!monitorRunning) {
        const res = await fetch('/api/monitor/start', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok' || data.status === 'already_running') {
            monitorRunning = true;
            sessionActive  = true;    // ← з цього моменту показуємо live-події
            // Оновлюємо lastEventId щоб не пропустити і не задублювати
            const r2 = await fetch('/api/events?limit=1');
            const latest = await r2.json();
            if (latest.length) lastEventId = latest[0].id;
            document.getElementById('monitor-status').className = 'status-dot online';
            document.getElementById('btn-monitor').textContent = '⏹ Stop';
            document.getElementById('btn-monitor').classList.add('stop');
        } else {
            alert(data.message || 'Error');
        }
    } else {
        monitorRunning = false;
        sessionActive  = false;   // ← зупиняємо прийом live-подій
        document.getElementById('monitor-status').className = 'status-dot offline';
        document.getElementById('btn-monitor').textContent = '▶ Start';
        document.getElementById('btn-monitor').classList.remove('stop');
    }
}

// ===== ЕКСПОРТ =====
async function exportData(type) {
    const from = document.getElementById('dt-from').value;
    const to = document.getElementById('dt-to').value;
    const res = await fetch(`/api/export/${type}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            from: from ? from.replace('T', ' ') : null,
            to: to ? to.replace('T', ' ') : null,
        })
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `moon_attacks_${Date.now()}.${type}`; a.click();
}

// ===== LIVE ТРАЕКТОРИИ =====
async function loadLiveTrajectories() {
    const res = await fetch('/api/trajectories');
    const trajectories = await res.json();
    drawTrajectories(trajectories);
    if (!trajectories.length) alert('Not enough data for trajectories yet');
}

function clearTraj() {
    trajectoryLayers.forEach(l => map.removeLayer(l));
    trajectoryLayers = [];
}

// ===== POLLING — нові події кожні 3 сек =====
let lastEventId = 0;

async function pollNewEvents() {
    if (currentMode !== 'live') return;
    if (!sessionActive) return;   // ← не поллимо якщо Start не натиснутий
    try {
        const res = await fetch(`/api/events/new?since=${lastEventId}`);
        const newEvents = await res.json();
        if (newEvents.length > 0) {
            newEvents.forEach(event => {
                if (allEvents.find(e => e.id === event.id)) return;
                allEvents.unshift(event);
                addMarker(event);
                addEventCard(event, true);
                addFullPost(event, true);
            });
            lastEventId = Math.max(...newEvents.map(e => e.id));
            updateStats();
        }
    } catch(e) {}
}

// ===== ЗАВАНТАЖЕННЯ ІСТОРІЇ З TELEGRAM =====
async function loadFromTelegram() {
    const from = document.getElementById('dt-from').value;
    const to   = document.getElementById('dt-to').value;
    if (!from || !to) { alert('Вибери діапазон дат!'); return; }

    const cities = Array.from(document.querySelectorAll('.route-input'))
        .map(i => i.value.trim()).filter(v => v);

    const btn = document.getElementById('btn-tg-load');
    btn.disabled = true;
    btn.textContent = '⏳ Loading...';
    setProgress('⏳ Connecting to Telegram...');

    // Авто-сброс кнопки через 90 минут если history_done не пришёл
    setTimeout(() => {
        if (btn.disabled) {
            btn.disabled = false;
            btn.textContent = '📥 Load from Telegram';
            setProgress('');
            loadHistorical(); // всё равно грузим что есть в БД
        }
    }, 90 * 60 * 1000);

    try {
        const res = await fetch('/api/history/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from:   from.replace('T', ' '),
                to:     to.replace('T', ' '),
                cities: cities,
            })
        });
        const data = await res.json();
        if (data.status !== 'ok') {
            alert(data.message || 'Error');
            btn.disabled = false;
            btn.textContent = '📥 Load from Telegram';
            setProgress('');
        } else {
            const routeNote = cities.length
                ? ` · маршрут: ${cities.join(' → ')}`
                : ' · всі канали';
            setProgress(`⏳ ${data.channels} каналів${routeNote}...`);
            startHistoryPolling();  // ← починаємо polling прогресу
        }
    } catch(e) {
        alert('Network error: ' + e.message);
        btn.disabled = false;
        btn.textContent = '📥 Load from Telegram';
        setProgress('');
    }
}

function setProgress(msg) {
    const el = document.getElementById('history-progress');
    if (el) el.textContent = msg;
}

// ===== POLLING ПРОГРЕСУ ЗАВАНТАЖЕННЯ ІСТОРІЇ =====
let _historyPollTimer = null;

function startHistoryPolling() {
    stopHistoryPolling();
    _historyPollTimer = setInterval(async () => {
        try {
            const res  = await fetch('/api/history/status');
            const data = await res.json();

            if (data.running) {
                setProgress(`📡 [${data.current}/${data.total}] ${data.channel} — ${data.saved} збережено`);
            }

            if (data.done) {
                stopHistoryPolling();
                const btn = document.getElementById('btn-tg-load');
                if (btn) { btn.disabled = false; btn.textContent = '📥 Load from Telegram'; }
                setProgress(`✅ ${data.saved} нових подій — завантажую на карту...`);
                // Грузимо ВСЕ з БД за вибраний період
                await loadHistorical();
                setTimeout(() => setProgress(''), 4000);
            }
        } catch(e) {}
    }, 2000);
}

function stopHistoryPolling() {
    if (_historyPollTimer) { clearInterval(_historyPollTimer); _historyPollTimer = null; }
}

// SocketIO залишаємо як резерв
socket.on('history_progress', (data) => {
    setProgress(`📡 [${data.current}/${data.total}] ${data.channel} — ${data.saved} saved`);
});
socket.on('history_error', (data) => {
    console.warn('[HISTORY]', data.channel, ':', data.error);
});

// ===== ОЧИСТКА =====
async function clearAllEvents() {
    if (!confirm('Удалить ВСЕ события из базы? Каналы останутся.')) return;
    const res = await fetch('/api/events/clear', { method: 'DELETE' });
    const data = await res.json();
    clearMarkers();
    allEvents = [];
    document.getElementById('tab-feed').innerHTML = '';
    document.getElementById('tab-full').innerHTML = '';
    updateStats();
    alert(`✅ Удалено ${data.deleted} событий. База чистая.`);
}

// ===== СТАРТ =====
window.addEventListener('load', () => {
    loadLive();
    loadChannels();
    setInterval(pollNewEvents, 3000);
});
