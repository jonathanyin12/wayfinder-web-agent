"""
Scroll actions for navigating up and down a page.
"""

from playwright.async_api import Page

from agent.browser.core.page import browser_action


async def scroll_down(page: Page):
    """
    Scroll down the page by approximately 75% of the viewport height.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop + (window.innerHeight * 0.75);"
    )


async def scroll_up(page: Page):
    """
    Scroll up the page by approximately 75% of the viewport height.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop - (window.innerHeight * 0.75);"
    )


@browser_action
async def scroll(page: Page, direction: str):
    """
    Scroll the page in a specified direction.

    Args:
        page: The Playwright page
        direction: The direction to scroll ('up' or 'down')
    """
    if direction == "down":
        await scroll_down(page)
    elif direction == "up":
        await scroll_up(page)
