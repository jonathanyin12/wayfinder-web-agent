from typing import Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from agent.browser import (
    click_element,
    go_back,
    go_forward,
    go_to_url,
    hover_element,
    refresh,
    scroll_down,
    scroll_up,
    take_element_screenshot,
    take_screenshot,
    type,
    type_and_enter,
)


class AgentBrowser:
    def __init__(self):
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

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

            # Return an async wrapper that automatically passes self.page as first argument
            async def wrapper(*args, **kwargs):
                return await method(self.page, *args, **kwargs)

            return wrapper
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )
