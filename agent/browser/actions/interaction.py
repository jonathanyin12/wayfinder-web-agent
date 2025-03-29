"""
Interaction actions for clicking and hovering over elements.
"""

from playwright.async_api import Page

from agent.browser.core.page import browser_action


async def hover_element(page: Page, selector: str):
    """
    Hover over an element on the page.

    Args:
        page: The Playwright page
        selector: CSS selector for the element to hover over
    """
    await page.hover(selector)


@browser_action
async def click_element(page: Page, element_id: str):
    """
    Click an element on the page, with fallback to force click if normal click fails.

    Args:
        page: The Playwright page
        element_id: The unique ID of the element to click
    """
    try:
        selector = f'[data-gwa-id="gwa-element-{element_id}"]'
        await page.hover(selector)
        await page.click(selector, timeout=10000)

    except Exception as e:
        # If normal click fails, try force click
        print(f"Normal click failed, attempting force click: {str(e)}")
        await page.click(selector, force=True)
