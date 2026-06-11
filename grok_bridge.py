import asyncio
import logging
import time
from playwright.async_api import async_playwright, BrowserContext, Page
from config import (
    SESSION_DIR, GROK_URL,
    SEL_INPUT, SEL_SEND, SEL_RESPONSE, SEL_NEW_CHAT_BTN,
    RESPONSE_STABLE_TICKS, RESPONSE_TICK_INTERVAL, RESPONSE_TIMEOUT,
)

log = logging.getLogger(__name__)


class GrokBridge:
    def __init__(self):
        self.playwright = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._lock = asyncio.Lock()
        self._ready = False
        self._busy = False
        self._cancel = False
        self._start_time = time.time()

    async def start(self):
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(SESSION_DIR),
            headless=True,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        await self._open_grok()

    async def _open_grok(self):
        try:
            await self.page.goto(GROK_URL, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_selector(SEL_INPUT, timeout=15000)
            self._ready = True
            log.info("Grok ready")
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
        await self._open_grok()
        return self._ready

    async def _count_responses(self) -> int:
        els = await self.page.query_selector_all(SEL_RESPONSE)
        return len(els)

    async def _wait_for_new_response(self, prev_count: int) -> str:
        deadline = asyncio.get_event_loop().time() + RESPONSE_TIMEOUT
        while asyncio.get_event_loop().time() < deadline:
            if self._cancel:
                self._cancel = False
                return "⚠️ Cancelled."
            await asyncio.sleep(RESPONSE_TICK_INTERVAL)
            els = await self.page.query_selector_all(SEL_RESPONSE)
            if len(els) <= prev_count:
                continue
            last = els[-1]
            stable, prev_len = 0, -1
            while stable < RESPONSE_STABLE_TICKS:
                if self._cancel:
                    self._cancel = False
                    text = await last.inner_text()
                    return f"⚠️ Cancelled (partial response):\n\n{text.strip()}"
                await asyncio.sleep(RESPONSE_TICK_INTERVAL)
                new_text = await last.inner_text()
                stable = stable + 1 if len(new_text) == prev_len else 0
                prev_len = len(new_text)
            return (await last.inner_text()).strip()
        return "❌ Timeout: Grok did not respond within 2 minutes."

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
                    return "❌ Twitter session unavailable. Run login.py and copy browser_session to the server."
                prev_count = await self._count_responses()
                inp = await self.page.query_selector(SEL_INPUT)
                await inp.click()
                await inp.fill("")
                await inp.type(question, delay=25)
                send_btn = await self.page.query_selector(SEL_SEND)
                if send_btn:
                    await send_btn.click()
                else:
                    await inp.press("Enter")
                return await self._wait_for_new_response(prev_count)
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
                    await self.page.goto(GROK_URL, wait_until="domcontentloaded", timeout=20000)
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
        if self.playwright:
            await self.playwright.stop()
