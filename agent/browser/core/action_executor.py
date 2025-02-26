"""
Functions for executing agent actions on the browser.
"""

import logging
from typing import Dict

from playwright.async_api import Page

from ...models import AgentAction
from ..actions.extract import extract_page_information
from ..actions.input import type_and_enter, type_text
from ..actions.interaction import click_element
from ..actions.navigation import go_back, go_forward, refresh
from ..actions.scroll import scroll_down, scroll_up

# Set up logging
logger = logging.getLogger(__name__)


async def execute_action(
    page: Page, action: AgentAction, label_selectors: Dict[str, str]
) -> None:
    """
    Execute an agent action on the browser.

    Args:
        page: The Playwright page
        action: The agent action to execute
        label_selectors: Dictionary mapping labels to CSS selectors

    Raises:
        RuntimeError: If the browser page is not initialized
        Exception: If there's an error executing the action
    """
    if not page:
        raise RuntimeError("Browser page is not initialized")

    try:
        match action.name:
            case "CLICK":
                label_selector = label_selectors[str(action.args[0])]
                await click_element(page, label_selector)
            case "TYPE":
                label_selector = label_selectors[str(action.args[0])]
                text = action.args[1]
                await type_text(page, label_selector, text)
            case "TYPE_AND_SUBMIT":
                label_selector = label_selectors[str(action.args[0])]
                text = action.args[1]
                await type_and_enter(page, label_selector, text)
            case "EXTRACT":
                objective = action.args[0]
                await extract_page_information(page, objective)
            case "SCROLL_DOWN":
                await scroll_down(page)
            case "SCROLL_UP":
                await scroll_up(page)
            case "GO_BACK":
                await go_back(page)
            case "GO_FORWARD":
                await go_forward(page)
            case "REFRESH":
                await refresh(page)
            case "END":
                return
            case _:
                logger.warning(f"Unknown action: {action.name}")
    except Exception as e:
        logger.error(f"Error executing action {action.name}: {e}")
        raise
