"""
Navigation actions for browser page navigation.
"""

from playwright.async_api import Page


async def go_to_url(page: Page, url: str):
    """
    Navigate to a specific URL.

    Args:
        page: The Playwright page
        url: The URL to navigate to
    """
    await page.goto(url)


async def go_back(page: Page):
    """
    Navigate back to the previous page in history.

    Args:
        page: The Playwright page
    """
    await page.go_back()


async def go_forward(page: Page):
    """
    Navigate forward to the next page in history.

    Args:
        page: The Playwright page
    """
    await page.go_forward()


async def refresh(page: Page):
    """
    Refresh the current page.

    Args:
        page: The Playwright page
    """
    await page.reload()
