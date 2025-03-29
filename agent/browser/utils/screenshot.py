"""
Screenshot actions for capturing the page or specific elements.
"""

import base64
from pathlib import Path
from typing import Optional

from playwright.async_api import Page


async def take_screenshot_full_page(page: Page, save_path: Optional[str] = None) -> str:
    """
    Take a screenshot of the full page by temporarily extending the viewport.
    This avoids issues with fixed elements appearing multiple times.
    """
    # Store original viewport size
    original_viewport = await page.evaluate("""() => { 
        return {
            width: window.innerWidth,
            height: window.innerHeight
        }
    }""")

    # Get page dimensions
    page_width = await page.evaluate("document.body.scrollWidth")
    page_height = await page.evaluate("document.body.scrollHeight")

    # Save original scroll position
    original_position = await page.evaluate("window.scrollY")

    try:
        # Set viewport to full page size (with reasonable limits)
        max_dimension = 16384  # Most browsers have limits around this size
        if page_height > max_dimension:
            # Fall back to scrolling method if page is too large
            return await take_screenshot_full_page(page, save_path)

        # Resize viewport to fit the entire page
        await page.set_viewport_size({"width": page_width, "height": page_height})

        # Take the screenshot in one go
        screenshot = await page.screenshot(full_page=False)

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(screenshot)

        return base64.b64encode(screenshot).decode("utf-8")

    finally:
        # Always restore original viewport size and scroll position
        await page.set_viewport_size(
            {"width": original_viewport["width"], "height": original_viewport["height"]}
        )
        await page.evaluate(f"window.scrollTo(0, {original_position})")


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
    if full_page:
        # Try the extended viewport method first (cleaner results)
        try:
            return await take_screenshot_full_page(page, save_path)
        except Exception:
            # Fall back to the scrolling method if anything goes wrong
            return await take_screenshot_full_page(page, save_path)

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    screenshot = await page.screenshot(full_page=full_page, path=save_path)
    return base64.b64encode(screenshot).decode("utf-8")


async def take_element_screenshot(
    page: Page, element_id: str, save_path: Optional[str] = None
) -> str:
    """
    Take a screenshot of a specific element on the page.

    Args:
        page: The Playwright page
        element_id: The unique GWA ID for the element to capture
        save_path: Path to save the screenshot

    Returns:
        Base64-encoded string of the screenshot, or None if element not found
    """

    selector = f'[data-gwa-id="gwa-element-{element_id}"]'
    element = await page.query_selector(selector)

    if not element:
        raise ValueError(f"Element with ID {element_id} not found")

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    screenshot = await element.screenshot(path=save_path)
    return base64.b64encode(screenshot).decode("utf-8")
