"""
Input actions for interacting with form fields and text inputs.
"""

from playwright.async_api import Page

from agent.browser.core.page import browser_action


@browser_action
async def type_text(page: Page, selector: str, text: str, submit: bool = False):
    """
    Type text into an input field.

    Args:
        page: The Playwright page
        selector: CSS selector for the input element
        text: Text to type into the field
    """
    await page.fill(selector, text)
    if submit:
        await page.press(selector, "Enter")
