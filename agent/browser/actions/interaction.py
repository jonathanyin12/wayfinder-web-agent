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
    Handles elements that may be in iframes.

    Args:
        page: The Playwright page
        element_id: The unique ID of the element to click
    """
    selector = f'[data-gwa-id="gwa-element-{element_id}"]'

    try:
        # First try to find and click the element in the main frame
        if await page.locator(selector).count() > 0:
            await page.hover(selector, timeout=10000)
            await page.click(selector, timeout=10000)
            return

        # If not found in main frame, look for it in all frames
        for frame in page.frames:
            if await frame.locator(selector).count() > 0:
                await frame.hover(selector, timeout=10000)
                await frame.click(selector, timeout=10000)
                return

        # If we get here, element wasn't found in any frame
        raise Exception(f"Element with selector {selector} not found in any frame")

    except Exception as e:
        # If normal click fails, try force click in all frames
        print(f"Normal click failed, attempting force click: {str(e)}")

        try:
            # Try force click in main frame
            if await page.locator(selector).count() > 0:
                await page.click(selector, force=True)
                return

            # Try force click in all frames
            for frame in page.frames:
                if await frame.locator(selector).count() > 0:
                    await frame.click(selector, force=True)
                    return

            raise Exception(
                f"Element with selector {selector} not found in any frame for force click"
            )
        except Exception as force_error:
            print(f"Force click also failed: {str(force_error)}")
            raise
