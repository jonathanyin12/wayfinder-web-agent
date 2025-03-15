"""
Screenshot actions for capturing the page or specific elements.
"""

import base64
from pathlib import Path
from typing import Optional

from playwright.async_api import Page


async def take_screenshot(
    page: Page, save_path: Optional[str] = None, full_page: bool = False
) -> str:
    """
    Take a screenshot of the current page.

    Args:
        page: The Playwright page
        save_path: Path to save the screenshot
        full_page: Whether to capture the full page or just the viewport

    Returns:
        Base64-encoded string of the screenshot
    """
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    screenshot = await page.screenshot(full_page=full_page, path=save_path)
    return base64.b64encode(screenshot).decode("utf-8")


async def take_element_screenshot(
    page: Page, element_id: str, save_path: Optional[str] = None
) -> Optional[str]:
    """
    Take a screenshot of a specific element on the page.

    Args:
        page: The Playwright page
        element_id: The unique GWA ID for the element to capture
        save_path: Path to save the screenshot

    Returns:
        Base64-encoded string of the screenshot, or None if element not found
    """
    # First try to find the element directly
    selector = f'[data-gwa-id="gwa-element-{element_id}"]'
    element = await page.query_selector(selector)

    if element:
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        screenshot = await element.screenshot(path=save_path)
        return base64.b64encode(screenshot).decode("utf-8")
    return None
