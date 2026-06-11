# Grok Telegram Bridge

A Telegram bot that proxies conversations through Grok (X Premium) using Playwright browser automation.  
Supports multiple chats per user, persistent history, and multi-user isolation.  
Runs inside Docker, managed by systemd.

## Requirements

- Ubuntu 22.04+
- Docker + Docker Compose plugin
- X Premium subscription (required for Grok access)

## Project Structure

```
bot.py              — entry point, handler registration
config.py           — selectors and constants
grok_bridge.py      — Playwright automation layer
chat_store.py       — JSON-based chat history storage
handlers.py         — Telegram command and message handlers
login.py            — one-time Twitter authentication (run locally)
Dockerfile          — container definition
docker-compose.yml  — service definition with volumes and shm
grok-tg-bot.service — systemd unit that manages the Docker container
.github/
  workflows/
    ci-cd.yml       — CI lint + Docker build check; CD job is commented out
```

## Data Layout on Host

```
/opt/grok-tg-bot/
  .env
  docker-compose.yml
  data/
    browser_session/   ← Twitter session (never commit)
    chats/             ← per-user chat history (never commit)
```

## Setup & Deploy

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
```

### 2. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/grok-tg-bot.git /opt/grok-tg-bot
cd /opt/grok-tg-bot
```

### 3. Configure environment

```bash
cp .env.example .env
nano .env  # paste your TG_TOKEN
```

### 4. Authenticate with Twitter (run locally, needs a display)

```bash
pip install playwright python-dotenv
playwright install chromium
python login.py
# log in manually in the browser → press Enter
# browser_session/ folder will be created
```

Copy session to server:
```bash
scp -r ./browser_session root@YOUR_SERVER:/opt/grok-tg-bot/data/
```

### 5. Create data directories

```bash
mkdir -p /opt/grok-tg-bot/data/browser_session
mkdir -p /opt/grok-tg-bot/data/chats
```

### 6. Build and start with systemd

```bash
cp grok-tg-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now grok-tg-bot
systemctl status grok-tg-bot
```

systemd manages the Docker container. If the container crashes, systemd restarts it automatically.

### 7. View logs

```bash
journalctl -u grok-tg-bot -f
```

## Bot Commands

| Command | Description |
|---|---|
| `/new` | Start a new Grok chat |
| `/list` | List all saved chats |
| `/switch N` | Switch to chat N and load its history |
| `/rename N text` | Rename chat N |
| `/export N` | Download chat N as a .txt file |
| `/status` | Show session status and uptime |
| `/cancel` | Cancel a pending Grok response |
| `/menu` or `.menu` | Open the command menu |

## CI/CD

GitHub Actions workflow runs on every push:

| Job | Trigger | What it does |
|---|---|---|
| `lint` | every push | ruff, syntax check, secret leak check |
| `docker-build` | every push (after lint) | builds Docker image to verify it compiles |
| `deploy` | **disabled** | SSH deploy + systemd restart |

To enable auto-deploy, follow the instructions in `.github/workflows/ci-cd.yml` and uncomment the `deploy` job.

## Updates

```bash
cd /opt/grok-tg-bot
git pull
systemctl restart grok-tg-bot
```

## Important

- `browser_session/` contains Twitter cookies — **never commit to git**
- `chats/` contains user conversation history — **never commit to git**
- All Grok UI selectors are in `config.py` — update there if Twitter changes `data-testid` attributes
- Container uses `shm_size: 1gb` — required for Chromium stability on Twitter/Grok
