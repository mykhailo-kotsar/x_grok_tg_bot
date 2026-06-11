from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

TG_TOKEN = os.environ["TG_TOKEN"]

BASE_DIR = Path(__file__).parent
CHATS_DIR = BASE_DIR / "chats"
CHATS_DIR.mkdir(exist_ok=True)

SESSION_DIR = BASE_DIR / "browser_session"
SESSION_DIR.mkdir(exist_ok=True)

GROK_URL = "https://x.com/i/grok"

# Selectors — update here if Twitter changes them
SEL_INPUT        = "textarea[placeholder='Ask anything']"
SEL_RESPONSE     = "[data-testid='primaryColumn']"
SEL_NEW_CHAT_BTN = "[aria-label='New Chat']"

RESPONSE_STABLE_TICKS = 3
RESPONSE_TICK_INTERVAL = 1.5
RESPONSE_TIMEOUT = 120

CHAT_TITLE_MAX_LEN = 40

RESPONSE_STOP_MARKERS = ["Think Harder", "Auto", "See new posts"]
