from datetime import datetime
from typing import Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from .annotation import (
    ANNOTATE_PAGE_TEMPLATE,
    clear_annotations,
)
from .input import type, type_and_enter
from .interaction import click_element, hover_element
from .navigation import go_back, go_forward, go_to_url, refresh
from .screenshot import take_element_screenshot, take_screenshot
from .scroll import (
    get_pixels_above_below,
    scroll_down,
    scroll_up,
)
from .utils import get_base_url


class AgentBrowser:
    def __init__(self):
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.previous_page_url: str = ""
        self.previous_page_screenshot_base64: str = ""

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
            "get_pixels_above_below": get_pixels_above_below,
            "take_screenshot": take_screenshot,
            "take_element_screenshot": take_element_screenshot,
            "clear_annotations": clear_annotations,
        }

    async def launch(
        self, url: str = "https://google.com", headless: bool = False
    ) -> Tuple[BrowserContext, Page]:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--window-position=0,0",
            ],
        )
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 1000},
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
                    base64_screenshot = await method(
                        self.page, *args, save_path=save_path, **kwargs
                    )
                    return base64_screenshot
                return await method(self.page, *args, **kwargs)

            return wrapper
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    async def execute_action(self, action: str, label_selector: str, text: str = ""):
        # Save the previous page URL before executing the action in case the page changes
        self.previous_page_url = self.page.url

        match action:
            case "CLICK":
                await click_element(self.page, label_selector)
            case "TYPE":
                await type(self.page, label_selector, text)
            case "TYPE_AND_SUBMIT":
                await type_and_enter(self.page, label_selector, text)
            case "SCROLL_DOWN":
                await scroll_down(self.page)
            case "SCROLL_UP":
                await scroll_up(self.page)
            case "GO_BACK":
                await go_back(self.page)
            case "GO_FORWARD":
                await go_forward(self.page)
            case "REFRESH":
                await refresh(self.page)
            case "END":
                return

    def get_site_name(self) -> str:
        base_url = get_base_url(self.page.url)
        return base_url.replace("www.", "")

    async def annotate_page(self):
        self.label_selectors, self.label_simplified_htmls = await self.page.evaluate(
            ANNOTATE_PAGE_TEMPLATE
        )

    async def wait_for_page_load(self):
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as e:
            print(f"Error waiting for networkidle: {e}")
            pass

    def is_new_page(self) -> bool:
        """Check if the current page is different from the last page"""
        return self.previous_page_url != self.page.url
