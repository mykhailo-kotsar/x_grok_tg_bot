import asyncio
import json
import logging
import time
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config import (
    GROK_URL,
    SEL_INPUT, SEL_RESPONSE, SEL_NEW_CHAT_BTN,
    RESPONSE_STABLE_TICKS, RESPONSE_TICK_INTERVAL, RESPONSE_TIMEOUT,
)

log = logging.getLogger(__name__)

COOKIES_FILE = Path("/app/data/session_cookies.json")

STRIP_LINES = {
    "See new posts", "Think Harder", "Auto", "Think harder",
    "To view keyboard shortcuts, press question mark",
    "View keyboard shortcuts",
}


def _parse_response(text: str, question: str) -> str:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    result = []
    found_question = False
    for line in lines:
        if line in STRIP_LINES:
            continue
        if not found_question:
            if question.strip()[:30] in line or line in question.strip():
                found_question = True
            continue
        result.append(line)
    if not result:
        log.warning("Could not parse response, raw lines: %s", lines)
        return text.strip()
    return "\n".join(result).strip()


class GrokBridge:
    def __init__(self):
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._lock = asyncio.Lock()
        self._ready = False
        self._busy = False
        self._cancel = False
        self._start_time = time.time()

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        await self._create_context()
        await self._open_grok()

    async def _create_context(self):
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        if COOKIES_FILE.exists():
            cookies = json.loads(COOKIES_FILE.read_text())
            await self.context.add_cookies(cookies)
            log.info("Loaded %d cookies", len(cookies))
        self.page = await self.context.new_page()

    async def _open_grok(self):
        try:
            await self.page.goto(GROK_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            if "login" in self.page.url or "onboarding" in self.page.url:
                log.error("Redirected to login — cookies invalid or expired")
                self._ready = False
                return
            await self.page.wait_for_selector(SEL_INPUT, timeout=30000)
            self._ready = True
            log.info("Grok ready — URL: %s", self.page.url)
        except Exception as e:
            self._ready = False
            log.error("Failed to open Grok: %s", e)

    async def _ensure_ready(self) -> bool:
        if self._ready:
            try:
                await self.page.wait_for_selector(SEL_INPUT, timeout=5000)
                return True
            except Exception:
                pass
        await self._create_context()
        await self._open_grok()
        return self._ready

    async def _snapshot(self) -> str:
        col = await self.page.query_selector(SEL_RESPONSE)
        if not col:
            return ""
        return await col.inner_text()

    async def _wait_for_new_response(self, prev_text: str, question: str) -> str:
        deadline = asyncio.get_event_loop().time() + RESPONSE_TIMEOUT
        # Wait for real response to appear (ignore loading states)
        LOADING_MARKERS = ["Thinking about your request", "Generating", "Loading"]
        while asyncio.get_event_loop().time() < deadline:
            if self._cancel:
                self._cancel = False
                return "⚠️ Cancelled."
            await asyncio.sleep(RESPONSE_TICK_INTERVAL)
            col = await self.page.query_selector(SEL_RESPONSE)
            if not col:
                continue
            text = await col.inner_text()
            if text == prev_text:
                continue
            if any(m in text for m in LOADING_MARKERS):
                prev_text = text
                continue
            break
        else:
            return "❌ Timeout: Grok did not respond within 2 minutes."
        # Response appeared — now wait for it to stop growing
        last_text = ""
        stable = 0
        while asyncio.get_event_loop().time() < deadline:
            if self._cancel:
                self._cancel = False
                return "⚠️ Cancelled."
            await asyncio.sleep(RESPONSE_TICK_INTERVAL)
            col = await self.page.query_selector(SEL_RESPONSE)
            if not col:
                continue
            text = await col.inner_text()
            if text == last_text:
                stable += 1
            else:
                stable = 0
                last_text = text
            if stable >= RESPONSE_STABLE_TICKS:
                return _parse_response(text, question)
        return _parse_response(last_text, question)

    async def current_url(self) -> str:
        return self.page.url if self.page else GROK_URL

    def is_busy(self) -> bool:
        return self._busy

    def cancel(self):
        if self._busy:
            self._cancel = True

    def uptime(self) -> str:
        secs = int(time.time() - self._start_time)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return f"{h}h {m}m {s}s"

    async def ask(self, question: str) -> str:
        async with self._lock:
            self._busy = True
            self._cancel = False
            try:
                if not await self._ensure_ready():
                    return "❌ Twitter session unavailable. Re-run import_cookies.py and copy session_cookies.json to the server."
                snapshot = await self._snapshot()
                inp = await self.page.wait_for_selector(SEL_INPUT, timeout=10000)
                await inp.click()
                await inp.fill("")
                await inp.type(question, delay=25)
                await self.page.keyboard.press("Enter")
                return await self._wait_for_new_response(snapshot, question)
            except Exception as e:
                log.exception("ask() failed")
                self._ready = False
                return f"❌ Error: {e}"
            finally:
                self._busy = False

    async def new_chat(self) -> str | None:
        async with self._lock:
            if not await self._ensure_ready():
                return None
            try:
                btn = await self.page.query_selector(SEL_NEW_CHAT_BTN)
                if btn:
                    await btn.click()
                else:
                    await self.page.goto(GROK_URL, wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_selector(SEL_INPUT, timeout=10000)
                return self.page.url
            except Exception:
                log.exception("new_chat() failed")
                return None

    async def switch_to(self, url: str) -> bool:
        async with self._lock:
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_selector(SEL_INPUT, timeout=10000)
                self._ready = True
                return True
            except Exception:
                log.exception("switch_to() failed")
                self._ready = False
                return False

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
