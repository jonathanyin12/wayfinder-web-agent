"""
Functions for managing page state, including screenshots and annotations.
"""

import logging
from typing import Tuple

from playwright.async_api import Page

from ..actions.annotation import annotate_page
from ..actions.screenshot import take_screenshot

# Set up logging
logger = logging.getLogger(__name__)


async def wait_for_page_load(page: Page) -> None:
    """
    Wait for the page to finish loading.

    Args:
        page: The Playwright page
    """
    if not page:
        raise RuntimeError("Browser page is not initialized")

    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception as e:
        logger.warning(f"Error waiting for networkidle: {e}")


async def update_page_screenshots(
    page: Page, screenshot_folder: str, screenshot_index: int
) -> Tuple[str, str, int, list, list]:
    """
    Update the page screenshots.

    Args:
        page: The Playwright page
        screenshot_folder: Folder to save screenshots
        screenshot_index: Current screenshot index

    Returns:
        Tuple containing (current_screenshot_base64, annotated_screenshot_base64, new_screenshot_index, label_selectors, label_simplified_htmls)
    """
    if not page:
        raise RuntimeError("Browser page is not initialized")

    await wait_for_page_load(page)

    # Take regular screenshot
    save_path = f"{screenshot_folder}/screenshot_{screenshot_index}.png"
    screenshot_index += 1
    current_screenshot_base64 = await take_screenshot(page, save_path=save_path)

    # Annotate page and take another screenshot
    label_selectors, label_simplified_htmls = await annotate_page(page)

    save_path = f"{screenshot_folder}/screenshot_{screenshot_index}.png"
    screenshot_index += 1
    annotated_screenshot_base64 = await take_screenshot(page, save_path=save_path)

    return (
        current_screenshot_base64,
        annotated_screenshot_base64,
        screenshot_index,
        label_selectors,
        label_simplified_htmls,
    )


def is_new_page(current_url: str, previous_url: str) -> bool:
    """
    Check if the current page is different from the previous page.

    Args:
        current_url: The current page URL
        previous_url: The previous page URL

    Returns:
        True if the page URL has changed, False otherwise
    """
    return current_url != previous_url
