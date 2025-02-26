"""
Core browser implementation for the agent.

This module provides the main AgentBrowser class that handles browser initialization,
page navigation, and interaction with web elements through various actions.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ...models import AgentAction
from ..actions.annotation import clear_annotations
from ..actions.navigation import go_to_url
from ..actions.screenshot import take_element_screenshot, take_screenshot
from ..actions.scroll import get_pixels_above_below
from ..utils.page_info import (
    get_formatted_interactable_elements,
    get_formatted_page_position,
)
from ..utils.url import get_base_url
from .action_executor import execute_action
from .page_state import update_page_screenshots

# Set up logging
logger = logging.getLogger(__name__)


class AgentBrowser:
    """
    A browser controller for web agents.

    This class provides methods for browser initialization, page navigation,
    and interaction with web elements. It wraps Playwright functionality
    and provides a simplified interface for agent interactions.
    """

    def __init__(self):
        """Initialize the browser controller."""
        # Playwright resources
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Page state
        self.previous_page_url: str = ""
        self.previous_page_screenshot_base64: str = ""
        self.current_page_screenshot_base64: str = ""
        self.current_annotated_page_screenshot_base64: str = ""
        self.label_selectors: Dict[str, str] = {}
        self.label_simplified_htmls: Dict[str, Dict] = {}

        # Screenshot configuration
        self.screenshot_index = 0
        self.screenshot_folder = f"screenshots/{datetime.now().strftime('%Y%m%d_%H%M')}"

        # Map method names to their implementations for dynamic dispatch
        self._method_map = {
            "get_pixels_above_below": get_pixels_above_below,
            "take_screenshot": take_screenshot,
            "take_element_screenshot": take_element_screenshot,
            "clear_annotations": clear_annotations,
        }

    # Browser lifecycle methods
    # ------------------------------------------------------------------------

    async def launch(
        self, url: str = "https://google.com", headless: bool = False
    ) -> Tuple[BrowserContext, Page]:
        """
        Launch the browser and navigate to the initial URL.

        Args:
            url: The initial URL to navigate to
            headless: Whether to run the browser in headless mode

        Returns:
            A tuple containing the browser context and page
        """
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--window-position=0,0",
            ],
        )

        # Set up a realistic user agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 1000},
        )

        self.page = await self.context.new_page()
        await go_to_url(self.page, url)
        await self._update_page_screenshots()

        return self.context, self.page

    async def terminate(self):
        """Close browser and playwright resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    # Dynamic method resolution
    # ------------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic method resolution for browser actions.

        This allows calling action methods directly on the AgentBrowser instance.

        Args:
            name: The name of the method to call

        Returns:
            A wrapper function that calls the appropriate action method

        Raises:
            AttributeError: If the method name is not in the method map
        """
        if name in self._method_map:
            method = self._method_map[name]

            # Return an async wrapper that automatically passes self.page and screenshot_path for screenshot methods
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                if not self.page:
                    raise RuntimeError("Browser page is not initialized")

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

    # Action execution
    # ------------------------------------------------------------------------

    async def execute_action(self, action: AgentAction) -> None:
        """
        Execute an agent action on the browser.

        Args:
            action: The agent action to execute
        """
        if not self.page:
            raise RuntimeError("Browser page is not initialized")

        # Save the previous page URL and screenshot before executing the action
        self.previous_page_url = self.page.url
        self.previous_page_screenshot_base64 = self.current_page_screenshot_base64
        await self.clear_annotations()

        # Execute the action
        result = await execute_action(self.page, action, self.label_selectors)
        if result:
            formatted_result = f"Performed {action.name}: {result}"
        else:
            formatted_result = f"Performed {action.name}, outcome unknown"
        # Store the current page screenshot after the action completes
        await self._update_page_screenshots()

        return formatted_result

    # Page information methods
    # ------------------------------------------------------------------------

    def get_site_name(self) -> str:
        """
        Get the base site name from the current URL.

        Returns:
            The base domain name without 'www.'
        """
        if not self.page:
            raise RuntimeError("Browser page is not initialized")

        base_url = get_base_url(self.page.url)
        return base_url.replace("www.", "")

    # Page state management (private methods)
    # ------------------------------------------------------------------------

    async def _update_page_screenshots(self) -> None:
        """Update the current page screenshots and annotations."""
        if not self.page:
            raise RuntimeError("Browser page is not initialized")

        result = await update_page_screenshots(
            self.page, self.screenshot_folder, self.screenshot_index
        )

        self.current_page_screenshot_base64 = result[0]
        self.current_annotated_page_screenshot_base64 = result[1]
        self.screenshot_index = result[2]
        self.label_selectors = result[3]
        self.label_simplified_htmls = result[4]

    # Formatting methods for agent communication
    # ------------------------------------------------------------------------

    async def get_formatted_interactable_elements(self) -> str:
        """
        Get a formatted string of interactable elements on the page.

        Returns:
            A formatted string representation of interactable elements
        """
        if not self.page:
            raise RuntimeError("Browser page is not initialized")

        pixels_above_below = await self.get_pixels_above_below()
        return await get_formatted_interactable_elements(
            self.label_simplified_htmls, pixels_above_below
        )

    async def get_formatted_page_position(self) -> str:
        """
        Get a formatted string describing the current scroll position.

        Returns:
            A human-readable description of the current scroll position
        """
        if not self.page:
            raise RuntimeError("Browser page is not initialized")

        pixels_above_below = await self.get_pixels_above_below()
        return await get_formatted_page_position(pixels_above_below)
