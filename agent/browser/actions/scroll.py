"""
Scroll actions for navigating up and down a page.
"""

from playwright.async_api import Page

from agent.browser.core.page import browser_action


async def scroll_down(page: Page, amount: float = 0.75):
    """
    Scroll down the page by approximately a fraction of the viewport height.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        """(amount) => {
            (document.scrollingElement || document.body).scrollTop = 
                (document.scrollingElement || document.body).scrollTop + (window.innerHeight * amount);
        }""",
        amount,
    )


async def scroll_up(page: Page, amount: float = 0.75):
    """
    Scroll up the page by approximately a fraction of the viewport height.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        """(amount) => {
            (document.scrollingElement || document.body).scrollTop = 
                (document.scrollingElement || document.body).scrollTop - (window.innerHeight * amount);
        }""",
        amount,
    )


@browser_action
async def scroll(page: Page, direction: str, amount: float = 0.75):
    """
    Scroll the page in a specified direction.

    Args:
        page: The Playwright page
        direction: The direction to scroll ('up' or 'down')
        amount: The fraction of the page height to scroll. 0.75 is a good default. If you only want to scroll a little, use 0.4.
    """
    if direction == "down":
        await scroll_down(page, amount)
    elif direction == "up":
        await scroll_up(page, amount)
