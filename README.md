<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-2.x-green?style=for-the-badge&logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Telegram-MTProto-26A5E4?style=for-the-badge&logo=telegram&logoColor=white">
  <img src="https://img.shields.io/badge/Claude-AI-a855f7?style=for-the-badge&logo=anthropic&logoColor=white">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge">
</p>

<h1 align="center">🌙 MooN Attacks</h1>
<p align="center"><b>Real-time military threat intelligence platform</b></p>
<p align="center">Monitor Telegram channels · AI-powered analysis · Interactive maps · Intelligence reports</p>

---

## What is MooN Attacks?

MooN Attacks is an open-source OSINT platform for monitoring military events in real time via Telegram channels. It automatically collects messages, classifies events (explosions, drones, missiles, etc.), plots them on an interactive map, and generates AI-powered intelligence reports.

> Built for analysts, researchers and journalists covering conflict zones.

---

## Features

| Feature | Description |
|---------|-------------|
| 🗺️ **Live Map** | Real-time event markers on an interactive map (RF territory filter) |
| 📰 **Live Feed** | Chronological feed with filters by event type and city |
| 🤖 **AI Reports** | Claude AI generates full intelligence reports with sources |
| 📡 **Telegram Monitor** | Real-time monitoring of multiple channels simultaneously |
| 📥 **History Load** | Load historical messages from Telegram for any time range |
| 🛣️ **Route Tracking** | Track attack routes across multiple cities |
| 📊 **Export** | Export to Word / HTML / PDF / JSON / CSV |
| 🌙 **Splash Screen** | Animated 3D Moon with Three.js |

---

## Quick Start

### 1. Clone the repository

\\\ash
# Via GitHub CLI
gh repo clone SiLiN-ua/MooN-Attacks

# Via Git
git clone https://github.com/SiLiN-ua/MooN-Attacks
\\\

### 2. Install dependencies

\\\ash
pip install -r requirements.txt
\\\

### 3. Configure API keys

\\\ash
cp .env.example .env
\\\

Edit .env and fill in your credentials:

\\\env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=+380XXXXXXXXX
ANTHROPIC_API_KEY=your_anthropic_api_key
\\\

> **Get Telegram API keys:** https://my.telegram.org/apps
> **Get Anthropic API key:** https://console.anthropic.com

### 4. Authenticate Telegram (first time only)

\\\ash
python auth_telegram.py
\\\

### 5. Run

\\\ash
python app.py
\\\

Open in browser: **http://localhost:5001**

---

## Project Structure

\\\
MooN-Attacks/
├── app.py                  # Flask server & API routes
├── auth_telegram.py        # Telegram authentication
├── requirements.txt        # Dependencies
├── .env.example            # Environment template
├── core/
│   ├── db.py               # Database models (Peewee + SQLite)
│   ├── telegram_monitor.py # Telegram client (Telethon)
│   ├── reporter.py         # AI report generation (Claude)
│   ├── geo_parser.py       # City & coordinate extraction
│   └── trajectory.py       # Attack route analysis
├── templates/
│   ├── splash.html         # Landing page (3D Moon)
│   ├── index.html          # Main map page
│   ├── feed.html           # Live event feed
│   ├── report.html         # AI intelligence report
│   └── channel.html        # Channel posts page
└── static/
    ├── js/main.js          # Map logic & UI
    └── css/                # Styles
\\\

---

## How It Works

\\\
Telegram Channels
      ↓
  Telethon (MTProto) — real-time monitoring or history load
      ↓
  Platform code — classifies event type, city, coordinates
      ↓
  SQLite Database (Peewee ORM)
      ↓
     ┌─────────────────────┐
     ↓                     ↓
Leaflet Map           Live Feed
(RF territory)        (all events)
     ↓
  Claude AI → Intelligence Report
  (web search + source links + analysis)
\\\

---

## Pages

| URL | Description |
|-----|-------------|
| / | Splash screen with animated Moon |
| /map | Live interactive map |
| /feed | Live event feed |
| /report | AI intelligence report generator |
| /channel/<name> | Posts from a specific channel |

---

## Requirements

- Python 3.10+
- Telegram account (for MTProto access)
- Anthropic API key (Claude) — for AI reports
- Internet connection for map tiles (CartoDB)

---

## License

MIT License — free to use, modify and distribute.

---

<p align="center">
  Made by <a href="https://github.com/SiLiN-ua">Yehor Selin (SiLiN)</a> •
  <a href="https://www.linkedin.com/in/yehor-selin/">LinkedIn</a>
</p>
