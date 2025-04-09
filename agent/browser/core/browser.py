"""
Core browser implementation for the agent.

This module provides the main AgentBrowser class that handles browser initialization,
page navigation, and interaction with web elements through various actions.
"""

import logging
from typing import List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from agent.browser.core.page import AgentBrowserPage
from agent.llm.client import LLMClient
from agent.models import AgentAction

# Set up logging
logger = logging.getLogger(__name__)


class AgentBrowser:
    """
    A browser controller for web agents.

    This class provides methods for browser initialization, page navigation,
    and interaction with web elements. It wraps Playwright functionality
    and provides a simplified interface for agent interactions.
    """

    def __init__(
        self,
        initial_url: str,
        output_dir: str,
        headless: bool,
    ):
        """Initialize the browser controller."""
        # Playwright resources
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

        self.current_page_index = 0
        self.pages: List[AgentBrowserPage] = []

        self.llm_client = LLMClient()

        self.output_dir = output_dir
        self.initial_url = initial_url
        self.headless = headless

    # Browser lifecycle methods
    # ------------------------------------------------------------------------

    async def launch(self) -> None:
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
            headless=self.headless,
            args=[
                "--window-position=0,0",
            ],
        )

        # Set up a realistic user agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1200, "height": 1600},
        )

        await self.create_new_page(self.initial_url)

        self.context.on("page", self.handle_new_page_event)

    async def terminate(self):
        """Close browser and playwright resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def create_new_page(self, url: str):
        """Create a new page in the browser."""
        if not self.context:
            raise RuntimeError("Browser has not been initialized")

        page = await self.context.new_page()
        browser_page = AgentBrowserPage(page, self.llm_client, self.output_dir)
        self.pages.append(browser_page)
        self.current_page_index = len(self.pages) - 1

        await browser_page.go_to_url(url)
        await browser_page.update_page_state()

    async def handle_new_page_event(self, page: Page):
        """Handle page events."""
        logger.info("New tab opened")
        browser_page = AgentBrowserPage(page, self.llm_client, self.output_dir)
        self.pages.append(browser_page)
        self.current_page_index = len(self.pages) - 1
        await browser_page.update_page_state()

    # Action execution
    # ------------------------------------------------------------------------

    async def execute_action(self, action: AgentAction) -> str:
        """
        Execute an agent action on the browser.

        Args:
            action: The agent action to execute

        Returns:
            A string representation of the action result
        """

        action_response = ""
        if action.name == "end_task":
            pass
        elif action.name == "switch_tab":
            await self.switch_tab(action.args["tab_index"])
        else:
            action_response = await getattr(self.current_page, action.name)(
                **action.args
            )

        # Update the browser state after the action completes
        await self.current_page.update_page_state(
            force_update_page_overview=action.name == "click_element"
        )

        return action_response

    # Page state management (private methods)
    # ------------------------------------------------------------------------

    async def switch_tab(self, tab_index: int):
        """
        Switch to a specific browser tab by index.

        Args:
            tab_index: The index of the tab to switch to (0-based)
        """

        if 0 <= tab_index < len(self.pages):
            target_page = self.pages[tab_index]
            self.current_page_index = tab_index
            await target_page.page.bring_to_front()
        else:
            raise IndexError(
                f"Tab index {tab_index} out of range. Available tabs: {len(self.pages)}"
            )

    async def check_for_captcha(self) -> bool:
        """Check if a captcha is present on the current page."""
        current_page = self.pages[self.current_page_index]
        return await current_page.check_for_captcha()

    async def update_page_state(self):
        """Update the page state for all pages."""
        await self.current_page.update_page_state(force_update_page_overview=True)

    @property
    def current_page(self) -> AgentBrowserPage:
        """
        Get the current active browser page.

        Returns:
            The current AgentBrowserPage instance

        Raises:
            IndexError: If there are no open pages
        """
        if not self.pages:
            raise IndexError("No browser pages are open")
        return self.pages[self.current_page_index]
