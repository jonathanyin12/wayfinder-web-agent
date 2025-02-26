import json
from datetime import datetime
from typing import Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ..models import AgentAction
from .annotation import (
    ANNOTATE_PAGE_TEMPLATE,
    clear_annotations,
)
from .extract import extract_page_information
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
        self.current_page_screenshot_base64: str = ""
        self.current_annotated_page_screenshot_base64: str = ""

        self.screenshot_index = 0
        self.screenshot_folder = f"screenshots/{datetime.now().strftime('%Y%m%d_%H%M')}"

        # Map method names to their implementations
        self._method_map = {
            "type": type,
            "type_and_enter": type_and_enter,
            "click": click_element,
            "hover": hover_element,
            "extract": extract_page_information,
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

        await self.update_page_screenshots()

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

    async def execute_action(self, action: AgentAction):
        # Save the previous page URL and screenshot before executing the action
        self.previous_page_url = self.page.url
        self.previous_page_screenshot_base64 = self.current_page_screenshot_base64
        await self.clear_annotations()

        match action.name:
            case "CLICK":
                label_selector = self.label_selectors[str(action.args[0])]
                await click_element(self.page, label_selector)
            case "TYPE":
                label_selector = self.label_selectors[str(action.args[0])]
                text = action.args[1]
                await type(self.page, label_selector, text)
            case "TYPE_AND_SUBMIT":
                label_selector = self.label_selectors[str(action.args[0])]
                text = action.args[1]
                await type_and_enter(self.page, label_selector, text)
            case "EXTRACT":
                objective = action.args[0]
                await extract_page_information(self.page, objective)
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

        # Wait for any page load/navigation to complete
        await self.wait_for_page_load()

        # Store the current page screenshot after the action completes
        await self.update_page_screenshots()

    def get_site_name(self) -> str:
        base_url = get_base_url(self.page.url)
        return base_url.replace("www.", "")

    async def annotate_page(self):
        self.label_selectors, self.label_simplified_htmls = await self.page.evaluate(
            ANNOTATE_PAGE_TEMPLATE
        )

    async def update_page_screenshots(self):
        self.current_page_screenshot_base64 = await self.take_screenshot()
        await self.annotate_page()
        self.current_annotated_page_screenshot_base64 = await self.take_screenshot()

    async def wait_for_page_load(self):
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as e:
            print(f"Error waiting for networkidle: {e}")
            pass

    def is_new_page(self) -> bool:
        """Check if the current page is different from the last page"""
        return self.previous_page_url != self.page.url

    async def get_formatted_interactable_elements(self) -> str:
        pixels_above, pixels_below = await self.get_pixels_above_below()

        has_content_above = pixels_above > 0
        has_content_below = pixels_below > 0

        elements_text = json.dumps(self.label_simplified_htmls, indent=4)
        if elements_text:
            if has_content_above:
                elements_text = f"... {pixels_above} pixels above - scroll up to see more ...\n{elements_text}"
            else:
                elements_text = f"[Top of page]\n{elements_text}"
            if has_content_below:
                elements_text = f"{elements_text}\n... {pixels_below} pixels below - scroll down to see more ..."
            else:
                elements_text = f"{elements_text}\n[Bottom of page]"
        else:
            elements_text = "None"

        return elements_text

    async def get_formatted_page_position(self) -> str:
        pixels_above, pixels_below = await self.get_pixels_above_below()
        has_content_above = pixels_above > 0
        has_content_below = pixels_below > 0

        if has_content_above and has_content_below:
            page_position = "You are in the middle of the page."
        elif has_content_above:
            page_position = "You are at the top of the page."
        elif has_content_below:
            page_position = "You are at the bottom of the page."
        else:
            page_position = (
                "The entire page is visible. No scrolling is needed/possible."
            )

        return page_position
