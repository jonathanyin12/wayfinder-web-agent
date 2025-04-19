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
    # Get page dimensions
    page_height = await page.evaluate("document.body.scrollHeight")

    # Handle PDF pages (which often report height as 0)
    if page_height == 0:
        # Check if this is a PDF page
        is_pdf = await page.evaluate(
            "document.querySelector('embed[type=\"application/pdf\"]') !== null || document.querySelector('object[type=\"application/pdf\"]') !== null"
        )
        if is_pdf:
            print("PDF detected, using default PDF capture approach")
            # For PDFs, we'll use Playwright's built-in full_page option
            screenshot = await page.screenshot(full_page=False)
            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(screenshot)
            return base64.b64encode(screenshot).decode("utf-8")

    # Save original scroll position
    original_position = await page.evaluate("window.scrollY")

    # Scroll through the page to ensure all lazy-loaded content is loaded
    # await page.evaluate("""
    #     async () => {
    #         // Save original scroll position
    #         const originalPosition = window.scrollY;

    #         // Scroll through the entire page
    #         await new Promise((resolve) => {
    #             let totalHeight = 0;
    #             const distance = 100;
    #             const timer = setInterval(() => {
    #                 window.scrollBy(0, distance);
    #                 totalHeight += distance;

    #                 if(totalHeight >= document.body.scrollHeight){
    #                     clearInterval(timer);
    #                     resolve();
    #                 }
    #             }, 10);
    #         });

    #         // Restore original scroll position
    #         window.scrollTo(0, originalPosition);
    #     }
    # """)

    # Short delay to ensure everything is settled
    await page.wait_for_timeout(500)

    try:
        # Resize viewport to fit the entire page
        # Set a maximum height for the viewport to avoid issues with extremely long pages
        # Most browsers have limits on viewport dimensions
        max_viewport_height = 16384  # Common browser limit is around 16384 pixels
        viewport_height = min(page_height, max_viewport_height)

        await page.set_viewport_size({"width": 1200, "height": viewport_height})

        # Take the screenshot in one go
        screenshot = await page.screenshot(full_page=False)

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(screenshot)

        return base64.b64encode(screenshot).decode("utf-8")

    finally:
        # Always restore original viewport size and scroll position
        await page.set_viewport_size({"width": 1200, "height": 1600})
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
            pass

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    screenshot = await page.screenshot(full_page=False, path=save_path)
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

    # First try to find the element in the main frame
    element = await page.query_selector(selector)

    if element:
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        screenshot = await element.screenshot(path=save_path)
        return base64.b64encode(screenshot).decode("utf-8")

    # If not found in main frame, look for it in all frames
    for frame in page.frames:
        element = await frame.query_selector(selector)
        if element:
            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            screenshot = await element.screenshot(path=save_path)
            return base64.b64encode(screenshot).decode("utf-8")

    # If we get here, element wasn't found in any frame
    raise ValueError(f"Element with ID {element_id} not found in any frame")
