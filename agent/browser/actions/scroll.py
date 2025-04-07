"""
Scroll actions for navigating up and down a page.
"""

from playwright.async_api import Page

from agent.llm.client import LLMClient

llm_client = LLMClient()


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


async def page_at_bottom(page: Page) -> bool:
    """Check if the page is at the bottom"""
    return await page.evaluate(
        """() => {
            const scrollingElement = document.scrollingElement || document.body;
            return scrollingElement.scrollTop >= (scrollingElement.scrollHeight - window.innerHeight);
        }"""
    )
