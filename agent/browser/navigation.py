from playwright.async_api import Page


async def go_to_url(page: Page, url: str):
    await page.goto(url)


async def go_back(page: Page):
    await page.go_back()


async def go_forward(page: Page):
    await page.go_forward()


async def refresh(page: Page):
    await page.reload()
