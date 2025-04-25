"""
Navigation actions for browser page navigation.
"""

from playwright.async_api import Page

from web_agent.browser.core.page import browser_action


@browser_action
async def go_to_url(page: Page, url: str):
    """
    Navigate to a specific URL.

    Args:
        page: The Playwright page
        url: The URL to navigate to
    """
    await page.goto(url)


@browser_action
async def navigate(page: Page, direction: str):
    """
    Navigate the browser in a specified direction.
    """
    if direction == "back":
        await go_back(page)
    elif direction == "forward":
        await go_forward(page)


async def go_back(page: Page):
    """
    Navigate back to the previous page in history.

    Args:
        page: The Playwright page
    """
    previous_url = page.url
    await page.go_back()
    if page.url == previous_url:
        await page.go_back()


async def go_forward(page: Page):
    """
    Navigate forward to the next page in history.

    Args:
        page: The Playwright page
    """
    previous_url = page.url
    await page.go_forward()
    if page.url == previous_url:
        await page.go_forward()
