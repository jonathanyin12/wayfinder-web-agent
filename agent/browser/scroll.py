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
            const h = document.documentElement;
            const scrollTop = h.scrollTop || document.body.scrollTop;
            return scrollTop;
        }"""
    )
    pixels_below = await page.evaluate(
        """() => {
            const h = document.documentElement;
            const scrollTop = h.scrollTop || document.body.scrollTop;
            const scrollHeight = h.scrollHeight || document.body.scrollHeight;
            const clientHeight = h.clientHeight;
            return Math.max(0, scrollHeight - clientHeight - scrollTop);
        }"""
    )
    return pixels_above, pixels_below
