from playwright.async_api import Page


async def type(page: Page, selector: str, text: str, wait_time: int = 1000):
    await page.fill(selector, text)
    await page.wait_for_timeout(wait_time)


async def type_and_enter(page: Page, selector: str, text: str, wait_time: int = 1000):
    await page.fill(selector, text)
    await page.press(selector, "Enter")
    await page.wait_for_timeout(wait_time)
