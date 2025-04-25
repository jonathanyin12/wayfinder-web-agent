"""
Input actions for interacting with form fields and text inputs.
"""

from playwright.async_api import Page

from web_agent.browser.core.page import browser_action


@browser_action
async def type_text(page: Page, element_id: str, text: str, submit: bool = False):
    """
    Type text into an input field.

    Args:
        page: The Playwright page
        element_id: The unique ID for the input element
        text: Text to type into the field
    """
    # Format the selector properly based on input type
    selector = f'[data-gwa-id="gwa-element-{element_id}"]'

    await page.fill(selector, text)
    if submit:
        await page.press(selector, "Enter")
