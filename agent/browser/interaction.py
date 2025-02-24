from playwright.async_api import Page


async def hover_element(page: Page, selector: str):
    await page.hover(selector)


async def click_element(page: Page, selector: str):
    try:
        # First try normal click
        await page.click(selector, timeout=10000)
    except Exception as e:
        # If normal click fails, try force click
        print(f"Normal click failed, attempting force click: {str(e)}")
        await page.click(selector, force=True)
