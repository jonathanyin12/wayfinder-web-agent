"""
Input actions for interacting with form fields and text inputs.
"""

from playwright.async_api import Page


async def type_text(page: Page, selector: str, text: str):
    """
    Type text into an input field.

    Args:
        page: The Playwright page
        selector: CSS selector for the input element
        text: Text to type into the field
    """
    await page.fill(selector, text)


async def type_and_enter(page: Page, selector: str, text: str):
    """
    Type text into an input field and press Enter.

    Args:
        page: The Playwright page
        selector: CSS selector for the input element
        text: Text to type into the field
    """
    await page.fill(selector, text)
    await page.press(selector, "Enter")
