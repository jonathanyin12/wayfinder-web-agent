"""
Interaction actions for clicking and hovering over elements.
"""

from playwright.async_api import Page


async def hover_element(page: Page, selector: str):
    """
    Hover over an element on the page.

    Args:
        page: The Playwright page
        selector: CSS selector for the element to hover over
    """
    await page.hover(selector)


async def click_element(page: Page, selector: str):
    """
    Click an element on the page, with fallback to force click if normal click fails.

    Args:
        page: The Playwright page
        selector: CSS selector for the element to click
    """
    try:
        # First try normal click
        await page.click(selector, timeout=10000)
    except Exception as e:
        # If normal click fails, try force click
        print(f"Normal click failed, attempting force click: {str(e)}")
        await page.click(selector, force=True)
