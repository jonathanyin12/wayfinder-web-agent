from pathlib import Path
from typing import Optional

from playwright.async_api import Page


async def take_screenshot(page: Page, save_path: str, full_page: bool = False) -> bytes:
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    screenshot = await page.screenshot(full_page=full_page, path=save_path)
    return screenshot


async def take_element_screenshot(
    page: Page, selector: str, save_path: str
) -> Optional[bytes]:
    element = await page.query_selector(selector)
    if element:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        screenshot = await element.screenshot(path=save_path)
        return screenshot
    return None
