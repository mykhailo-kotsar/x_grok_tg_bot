"""
Run this ONCE locally (requires a display) to authenticate with Twitter.
The session is saved to ./browser_session/ and reused by bot.py headlessly.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_DIR = Path("./browser_session")
SESSION_DIR.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(SESSION_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://x.com/login")
        print("Log in to Twitter in the browser window that opened.")
        print("Press Enter here once you are logged in...")
        input()
        await page.goto("https://x.com/i/grok")
        try:
            await page.wait_for_selector("div[contenteditable='true']", timeout=15000)
            print("✅ Session saved. You can now run bot.py")
        except Exception:
            print("⚠️  Grok did not load — check your X Premium subscription")
        await context.close()


asyncio.run(main())
