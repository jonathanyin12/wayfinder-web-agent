from playwright.async_api import Page

async def scroll_down(page: Page):
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop - (window.innerHeight * 0.75);"
    )

async def scroll_up(page: Page):
    await page.evaluate(
        "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop + (window.innerHeight * 0.75);"
    )