"""
Utility functions for formatting page information for agent communication.
"""

import json
from typing import Dict, Tuple


async def get_formatted_interactable_elements(
    label_simplified_htmls: Dict, pixels_above_below: Tuple[int, int]
) -> str:
    """
    Get a formatted string of interactable elements on the page.

    Args:
        page: The Playwright page
        label_simplified_htmls: Dictionary of labeled HTML elements
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A formatted string representation of interactable elements
    """
    pixels_above, pixels_below = pixels_above_below
    has_content_above = pixels_above > 0
    has_content_below = pixels_below > 0

    elements_text = json.dumps(label_simplified_htmls, indent=4)
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


async def get_formatted_page_position(pixels_above_below: Tuple[int, int]) -> str:
    """
    Get a formatted string describing the current scroll position.

    Args:
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A human-readable description of the current scroll position
    """
    pixels_above, pixels_below = pixels_above_below
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
