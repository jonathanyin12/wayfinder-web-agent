"""
Screenshot actions for capturing the page or specific elements.
"""

import base64
import io
from pathlib import Path
from typing import Optional

from PIL import Image
from playwright.async_api import Page


async def take_screenshot_full_page(page: Page, save_path: Optional[str] = None) -> str:
    """
    Take a screenshot of the full page.
    Can't use page.screenshot(full_page=True) because it unfocuses the page, causing things like dropdowns to disappear.
    """
    # Scroll through the page to ensure lazy-loaded images are loaded
    # Take multiple screenshots while scrolling and stitch them together

    # Get viewport height
    viewport_height = await page.evaluate("window.innerHeight")
    page_height = await page.evaluate("document.body.scrollHeight")

    # Save original scroll position
    original_position = await page.evaluate("window.scrollY")

    # Collect screenshots
    screenshots = []
    scroll_positions = []
    current_position = 0

    while current_position < page_height:
        # Scroll to position
        await page.evaluate(f"window.scrollTo(0, {current_position})")
        await page.wait_for_timeout(100)  # Wait for any lazy-loaded content

        # Get actual scroll position (may differ from requested position)
        actual_position = await page.evaluate("window.scrollY")
        scroll_positions.append(actual_position)

        # Take screenshot of current viewport
        screenshot_bytes = await page.screenshot(full_page=False)
        screenshot_image = Image.open(io.BytesIO(screenshot_bytes))
        screenshots.append(screenshot_image)

        # Move to next position
        current_position += viewport_height
        # For the last iteration, adjust to capture exactly the bottom of the page
        if (
            current_position < page_height
            and current_position + viewport_height > page_height
        ):
            current_position = page_height - viewport_height

    # Scroll back to original position
    await page.evaluate(f"window.scrollTo(0, {original_position})")

    # Stitch images together
    if screenshots:
        # Create a new image with the full height
        full_width = screenshots[0].width
        full_image = Image.new("RGB", (full_width, page_height))

        # Paste each screenshot at the appropriate position based on actual scroll positions
        for i, img in enumerate(screenshots):
            full_image.paste(img, (0, scroll_positions[i]))

        # Convert stitched image to bytes
        img_byte_array = io.BytesIO()
        full_image.save(img_byte_array, format="PNG")
        screenshot = img_byte_array.getvalue()
    else:
        # Fallback to regular screenshot if no images were collected
        screenshot = await page.screenshot(full_page=True)

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(screenshot)
    return base64.b64encode(screenshot).decode("utf-8")


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
