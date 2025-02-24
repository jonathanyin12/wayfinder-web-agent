from playwright.async_api import Page


async def type(page: Page, selector: str, text: str):
    await page.fill(selector, text)


async def type_and_enter(page: Page, selector: str, text: str):
    await page.fill(selector, text)
    await page.press(selector, "Enter")
