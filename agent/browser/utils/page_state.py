from typing import Tuple

from playwright.async_api import Page


async def get_pixels_above_below(page: Page) -> Tuple[int, int]:
    """
    Get the number of pixels above and below the current viewport.

    Args:
        page: The Playwright page

    Returns:
        A tuple containing (pixels_above, pixels_below)
    """
    pixels_above = await page.evaluate(
        """() => {
            const scrollingElement = document.scrollingElement || document.body;
            return scrollingElement.scrollTop;
        }"""
    )
    pixels_below = await page.evaluate(
        """() => {
            const scrollingElement = document.scrollingElement || document.body;
            const scrollTop = scrollingElement.scrollTop;
            const scrollHeight = scrollingElement.scrollHeight;
            const clientHeight = window.innerHeight;
            return Math.max(0, scrollHeight - clientHeight - scrollTop);
        }"""
    )
    return pixels_above, pixels_below
