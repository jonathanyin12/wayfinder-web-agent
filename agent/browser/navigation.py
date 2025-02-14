from playwright.async_api import Page

async def go_to_url(page: Page, url: str, wait_until: str = "networkidle"):
    await page.goto(url, wait_until=wait_until)

async def go_back(page: Page, wait_until: str = "networkidle"):
    await page.go_back(wait_until=wait_until)

async def go_forward(page: Page, wait_until: str = "networkidle"):
    await page.go_forward(wait_until=wait_until)

async def refresh(page: Page):
    await page.reload()
