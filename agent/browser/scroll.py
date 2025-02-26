from typing import Tuple

from playwright.async_api import Page


async def scroll_down(page: Page):
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop + (window.innerHeight * 0.75);"
    )


async def scroll_up(page: Page):
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop - (window.innerHeight * 0.75);"
    )


async def get_pixels_above_below(page: Page) -> Tuple[int, int]:
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
