from datetime import datetime
from typing import Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from .input import type, type_and_enter
from .interaction import click_element, hover_element
from .navigation import go_back, go_forward, go_to_url, refresh
from .screenshot import take_element_screenshot, take_screenshot
from .scroll import scroll_down, scroll_up


class AgentBrowser:
    def __init__(self):
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

        self.screenshot_index = 0
        self.screenshot_folder = f"screenshots/{datetime.now().strftime('%Y%m%d_%H%M')}"

        # Map method names to their implementations
        self._method_map = {
            "type": type,
            "type_and_enter": type_and_enter,
            "click": click_element,
            "hover": hover_element,
            "go_to": go_to_url,
            "go_back": go_back,
            "go_forward": go_forward,
            "refresh": refresh,
            "scroll_up": scroll_up,
            "scroll_down": scroll_down,
            "take_screenshot": take_screenshot,
            "take_element_screenshot": take_element_screenshot,
        }

    async def launch(
        self, url: str = "https://google.com", headless: bool = False
    ) -> Tuple[BrowserContext, Page]:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless, args=["--start-maximized"]
        )
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.context = await self.browser.new_context(
            no_viewport=True, user_agent=user_agent
        )
        self.page = await self.context.new_page()
        await self.go_to(url)

    async def terminate(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def __getattr__(self, name):
        if name in self._method_map:
            method = self._method_map[name]

            # Return an async wrapper that automatically passes self.page and screenshot_path for screenshot methods
            async def wrapper(*args, **kwargs):
                if name in ["take_screenshot", "take_element_screenshot"]:
                    save_path = f"{self.screenshot_folder}/screenshot_{self.screenshot_index}.png"
                    self.screenshot_index += 1
                    return await method(self.page, *args, save_path=save_path, **kwargs)
                return await method(self.page, *args, **kwargs)

            return wrapper
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )
