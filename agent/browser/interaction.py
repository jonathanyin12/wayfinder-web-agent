from playwright.async_api import Page


async def hover_element(page: Page, selector: str, wait_time: int = 1000):
    await page.hover(selector)
    await page.wait_for_timeout(wait_time)


async def click_element(page: Page, selector: str, wait_time: int = 1000):
    await page.click(selector)
    await page.wait_for_timeout(wait_time)
