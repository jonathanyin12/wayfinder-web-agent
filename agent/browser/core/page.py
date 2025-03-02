import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Tuple
from urllib.parse import urlparse

from playwright.async_api import Page

from agent.browser.utils.annotation import annotate_page, clear_annotations
from agent.browser.utils.page_state import get_pixels_above_below
from agent.browser.utils.screenshot import take_screenshot
from agent.llm.client import LLMClient

logger = logging.getLogger(__name__)


def browser_action(func):
    """Register a function as a browser action."""
    BrowserActions.register(func.__name__, func)
    return func


class BrowserActions:
    _registry = {}

    @classmethod
    def register(cls, name, func):
        cls._registry[name] = func

    @classmethod
    def get(cls, name):
        return cls._registry.get(name)


class AgentBrowserPage:
    def __init__(self, page: Page, llm_client: LLMClient, screenshot_folder: str):
        self.page = page
        self.llm_client = llm_client
        self.label_selectors = {}
        self.label_simplified_htmls = {}
        self.previous_screenshot_base64 = ""
        self.current_screenshot_base64 = ""
        self.current_screenshot_annotated_base64 = ""

        self.screenshot_folder = screenshot_folder

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic method resolution for browser actions.

        This allows calling action methods directly on the AgentBrowserPage instance.

        Args:
            name: The name of the method to call

        Returns:
            A wrapper function that calls the appropriate action method

        Raises:
            AttributeError: If the method name is not in the method map
        """
        action_func = BrowserActions.get(name)
        if action_func:
            # Return an async wrapper that automatically passes self.page
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                if not self.page:
                    raise RuntimeError("Browser page is not initialized")

                if "element_id" in kwargs:
                    selector = self.label_selectors.get(kwargs["element_id"])
                    if selector:
                        kwargs["selector"] = selector
                        del kwargs["element_id"]
                    else:
                        raise ValueError(
                            f"No selector found for element_id: {kwargs['element_id']}"
                        )

                return await action_func(self.page, *args, **kwargs)

            return wrapper
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    async def update_page_state(self) -> None:
        """
        Update the page state with the current screenshot and annotated screenshot.
        """
        await self.wait_for_page_load()

        self.previous_screenshot_base64 = self.current_screenshot_base64
        self.current_screenshot_base64 = await take_screenshot(
            self.page,
            save_path=f"{self.screenshot_folder}/screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
        )
        self.label_selectors, self.label_simplified_htmls = await annotate_page(
            self.page
        )
        self.current_screenshot_annotated_base64 = await take_screenshot(
            self.page,
            save_path=f"{self.screenshot_folder}/annotated_screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
        )
        await clear_annotations(self.page)

    def get_base_url(self) -> str:
        """
        Extract the base domain from a URL.

        Args:
            url: The full URL to parse

        Returns:
            The base domain (netloc) from the URL
        """
        parsed_url = urlparse(self.page.url)
        base_url = parsed_url.netloc
        return base_url

    def get_shortened_url(self, max_length: int = 75) -> str:
        """
        Create a shortened version of a URL for display purposes.

        Args:
            url: The full URL to shorten
            max_length: Maximum length of the shortened URL

        Returns:
            A shortened version of the URL
        """
        if not self.page.url or len(self.page.url) <= max_length:
            return self.page.url

        parsed_url = urlparse(self.page.url)

        # Keep the scheme and netloc (domain)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # If the path is too long, truncate it
        path = parsed_url.path
        query = f"?{parsed_url.query}" if parsed_url.query else ""
        fragment = f"#{parsed_url.fragment}" if parsed_url.fragment else ""

        remaining = path + query + fragment

        # If everything fits, return the full URL
        if len(base) + len(remaining) <= max_length:
            return self.page.url

        # Calculate how much of the path we can keep
        available_space = max_length - len(base) - 3  # 3 for "..."

        if available_space <= 0:
            # If we can't even fit the base + ellipsis, just truncate the base
            return base[: max_length - 3] + "..."

        # Truncate the path and add ellipsis
        return base + remaining[:available_space] + "..."

    async def check_for_captcha(self) -> bool:
        """
        Detect if a captcha is present on the page using LLM analysis.

        Returns:
            bool: True if a captcha is detected, False otherwise
        """
        if not self.page:
            raise RuntimeError("Browser page is not initialized")

        # Use the current screenshot to check for captcha
        # Create a prompt to detect captcha
        captcha_prompt = """Analyze this screenshot and determine if it contains a CAPTCHA challenge.
Look for:
- Visual puzzles or challenges
- Text asking to verify you're human
- Checkboxes for "I'm not a robot"
- Image selection challenges

Respond with a JSON object:
{
    "reasoning": "brief explanation of why you think this is or isn't a captcha",
    "is_captcha": true/false,
}
"""
        # Create message with image
        user_message = self.llm_client.create_user_message_with_images(
            captcha_prompt, [self.current_screenshot_base64]
        )

        # Make the LLM call with gpt-4o-mini
        response = await self.llm_client.make_call(
            [user_message], "gpt-4o-mini", timeout=10
        )
        response_json = json.loads(response)

        # Return the captcha detection result
        return response_json.get("is_captcha", False)

    async def get_pixels_above_below(self) -> Tuple[int, int]:
        """
        Get the number of pixels above and below the current viewport.
        """
        return await get_pixels_above_below(self.page)

    async def wait_for_page_load(self) -> None:
        """
        Wait for the page to finish loading.

        Args:
            page: The Playwright page
        """
        await asyncio.sleep(3)
        # try:
        #     await self.page.wait_for_load_state("networkidle", timeout=5000)
        # except Exception as e:
        #     logger.warning(f"Error waiting for networkidle: {e}")
