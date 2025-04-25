import json
from typing import List

from web_agent.models import BrowserTab


def get_formatted_interactable_elements(pixels_above, pixels_below, elements) -> str:
    """
    Get a formatted string of interactable elements on the page.

    Args:
        page: The Playwright page
        elements: Dictionary of labeled HTML elements
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A formatted string representation of interactable elements
    """
    element_descriptions = {
        element_id: element["simplified_html"]
        for element_id, element in elements.items()
    }
    has_content_above = pixels_above > 0
    has_content_below = pixels_below > 0

    # Format the elements in a more readable way
    elements_text = ""
    if element_descriptions:
        for element_id, html in element_descriptions.items():
            elements_text += f"- Element {element_id}: {html}\n"
        elements_text = elements_text.rstrip()  # Remove trailing newline
    if elements_text:
        if has_content_above:
            elements_text = f"... {pixels_above} pixels above - scroll up to see more ...\n{elements_text}"
        else:
            elements_text = f"[Top of page]\n{elements_text}"
        if has_content_below:
            elements_text = f"{elements_text}\n... {pixels_below} pixels below - scroll down to see more ..."
        else:
            elements_text = f"{elements_text}\n[Bottom of page]"
    else:
        elements_text = "None"

    return elements_text


def get_formatted_page_position(pixels_above, pixels_below) -> str:
    """
    Get a formatted string describing the current scroll position.

    Args:
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A human-readable description of the current scroll position
    """
    has_content_above = pixels_above > 0
    has_content_below = pixels_below > 0

    if has_content_above and has_content_below:
        page_position = "You are in the middle of the page."
    elif has_content_above:
        page_position = "You are at the bottom of the page."
    elif has_content_below:
        page_position = "You are at the top of the page."
    else:
        page_position = "The entire page is visible. No scrolling is needed/possible."

    return page_position


async def get_formatted_tabs(browser) -> List[BrowserTab]:
    """
    Get a formatted string of tabs in the browser.
    """
    tabs = []
    for i, page in enumerate(browser.pages):
        tabs.append(
            BrowserTab(
                index=i,
                title=await page.page.title(),
                url=page.get_shortened_url(),
                is_focused=browser.current_page_index == i,
            )
        )
    return tabs
