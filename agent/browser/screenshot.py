from playwright.async_api import Page
from pathlib import Path
from datetime import datetime
from typing import Optional


async def take_screenshot(
    page: Page,
    path: str = None,
    full_page: bool = False
) -> str:
    if path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"screenshots/screenshot_{timestamp}.png"
    
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=path, full_page=full_page)
    return path

async def take_element_screenshot(
    page: Page,
    selector: str,
    path: str = None
) -> Optional[str]:
    element = await page.query_selector(selector)
    if element:
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"screenshots/element_{timestamp}.png"
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        await element.screenshot(path=path)
        return path
    return None