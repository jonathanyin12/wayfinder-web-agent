from playwright.async_api import Page


async def scroll_down(page: Page):
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop + (window.innerHeight * 0.75);"
    )


async def scroll_up(page: Page):
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop - (window.innerHeight * 0.75);"
    )


async def get_scroll_percentage(page: Page) -> int | None:
    scroll_percentage = await page.evaluate(
        """() => {
            const h = document.documentElement;
            const scrollTop = h.scrollTop || document.body.scrollTop;
            const scrollHeight = h.scrollHeight || document.body.scrollHeight;
            const clientHeight = h.clientHeight;
            const total = scrollHeight - clientHeight;
            return total > 0 ? (scrollTop / total) * 100 : 0;
        }"""
    )
    return int(scroll_percentage) if not float("nan") else None
