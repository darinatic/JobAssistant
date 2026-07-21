"""Stealth browser wrapper around Patchright (undetected Playwright fork)."""

import asyncio
import json
import random
from pathlib import Path
from typing import Optional

from patchright.async_api import Browser, BrowserContext, Page, async_playwright

from src.utils.config import settings


USER_DATA_DIR = Path("browser_data")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_SG_CONTEXT_OPTIONS = {
    "viewport": {"width": 1920, "height": 1080},
    "user_agent": _DEFAULT_UA,
    "locale": "en-SG",
    "timezone_id": "Asia/Singapore",
    "geolocation": {"latitude": 1.3521, "longitude": 103.8198},
    "permissions": ["geolocation"],
    "color_scheme": "light",
    "device_scale_factor": 1,
}


class HumanBehavior:
    @staticmethod
    async def random_delay(min_ms: int = 500, max_ms: int = 2000):
        await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)

    @staticmethod
    async def typing_delay():
        await asyncio.sleep(random.uniform(0.05, 0.15))

    @staticmethod
    async def human_type(page: Page, selector: str, text: str):
        element = await page.wait_for_selector(selector)
        await element.click()
        for char in text:
            await page.keyboard.type(char)
            await HumanBehavior.typing_delay()

    @staticmethod
    async def human_click(page: Page, selector: str):
        element = await page.wait_for_selector(selector)
        box = await element.bounding_box()
        if box:
            x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            await page.mouse.click(x, y)
        else:
            await element.click()

    @staticmethod
    async def scroll_into_view(page: Page, selector: str):
        await page.evaluate(f"""
            document.querySelector('{selector}')?.scrollIntoView({{
                behavior: 'smooth',
                block: 'center'
            }});
        """)
        await HumanBehavior.random_delay(300, 800)

    @staticmethod
    async def smooth_scroll(page: Page, distance: int = 500):
        await page.evaluate(f"""
            window.scrollBy({{
                top: {distance},
                behavior: 'smooth'
            }});
        """)
        await HumanBehavior.random_delay(500, 1000)


class StealthBrowser:
    def __init__(self, headless: bool = False, via_browserbase: bool | None = None):
        self.headless = headless or settings.headless_mode
        self.slowmo = settings.browser_slowmo_ms
        # Route through a Browserbase cloud browser (survives datacenter-IP blocking
        # in production). Defaults to the config decision when not explicitly set.
        self.via_browserbase = (
            (settings.browserbase_enabled and settings.browserbase_scrapers)
            if via_browserbase is None else via_browserbase
        )

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._bb = None
        self._bb_session = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        if self.via_browserbase:
            await self._start_browserbase()
            return
        USER_DATA_DIR.mkdir(exist_ok=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slowmo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
            ],
        )
        self._context = await self._browser.new_context(**_SG_CONTEXT_OPTIONS)
        self._page = await self._context.new_page()
        await self._inject_stealth_scripts()

    async def _start_browserbase(self):
        """Connect to a Browserbase cloud browser over CDP (stealth handled remotely)."""
        from src.browser import browserbase as bb

        self._bb, self._bb_session = await bb.create_session()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(self._bb_session.connect_url)
        self._context = self._browser.contexts[0]
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def _inject_stealth_scripts(self):
        if not self._page:
            return

        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'zh-CN']
            });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

    async def close(self):
        if self.via_browserbase:
            # Remote context/page belong to Browserbase — just disconnect + release.
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            if self._bb_session:
                from src.browser import browserbase as bb
                await bb.release_session(self._bb, self._bb_session)
            return
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._context

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._context.new_page()

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000):
        await HumanBehavior.random_delay(500, 1500)
        await self.page.goto(url, wait_until=wait_until, timeout=timeout)
        await HumanBehavior.random_delay(1000, 3000)

    async def save_session(self, name: str = "default"):
        if not self._context:
            return
        session_file = USER_DATA_DIR / f"{name}_session.json"
        state = await self._context.storage_state()
        session_file.write_text(json.dumps(state, indent=2))

    async def load_session(self, name: str = "default") -> bool:
        session_file = USER_DATA_DIR / f"{name}_session.json"
        if not session_file.exists():
            return False

        state = json.loads(session_file.read_text())
        if self._context:
            await self._context.close()
        self._context = await self._browser.new_context(storage_state=state, **_SG_CONTEXT_OPTIONS)
        self._page = await self._context.new_page()
        await self._inject_stealth_scripts()
        return True

    async def screenshot(self, path: str | Path):
        await self.page.screenshot(path=str(path))


async def create_stealth_browser(headless: bool = False) -> StealthBrowser:
    browser = StealthBrowser(headless=headless)
    await browser.start()
    return browser
