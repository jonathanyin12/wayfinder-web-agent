"""
Annotation actions for labeling and identifying interactive elements on web pages.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from playwright.async_api import Page

from agent.browser.utils.dom_utils.load_js_file import load_js_file
from agent.browser.utils.screenshot import take_element_screenshot, take_screenshot
from agent.llm.client import LLMClient

llm_client = LLMClient()


async def preprocess_page(
    page: Page, output_dir: str
) -> Tuple[str, str, Dict[int, Dict[str, str]]]:
    """
    Preprocess the page and return the screenshot, bounding box screenshot, and element descriptions.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    screenshot_base64 = await take_screenshot(
        page,
        save_path=f"{output_dir}/screenshots/{timestamp}.png",
    )
    element_simplified_htmls = await find_interactive_elements(page)
    await draw_bounding_boxes(page, list(element_simplified_htmls.keys()))
    bounding_box_screenshot_base64 = await take_screenshot(
        page,
        save_path=f"{output_dir}/bounding_box_screenshots/{timestamp}.png",
    )
    await clear_bounding_boxes(page)
    elements = await get_element_descriptions(
        page, element_simplified_htmls, output_dir
    )

    return screenshot_base64, bounding_box_screenshot_base64, elements


async def find_interactive_elements(page: Page) -> Dict[int, str]:
    """
    Find and identify interactive elements on the page.
    This function adds data-gwa-id attributes to elements but does not draw visual annotations.

    Args:
        page: The Playwright page

    Returns:
        A dictionary mapping visible indices to simplified HTML representations
    """
    # Load the JavaScript file
    find_interactive_js = load_js_file("find_interactive_elements.js")

    html_dict = await page.evaluate(find_interactive_js)

    # Convert string keys to integers
    element_simplified_htmls = {int(k): v for k, v in html_dict.items()}

    return element_simplified_htmls


async def draw_bounding_boxes(page: Page, indices: List[int]) -> int:
    """
    Draw bounding boxes around elements with data-gwa-id attributes.

    Args:
        page: The Playwright page
        indices: List of specific element indices to annotate.

    Returns:
        Number of elements that were annotated
    """
    # Load the JavaScript file
    draw_bounding_boxes_js = load_js_file("draw_bounding_boxes.js")

    return await page.evaluate(draw_bounding_boxes_js, indices)


async def draw_bounding_box_around_element(page: Page, element_id: int) -> None:
    """
    Draw a bounding box around the element with the specified index.

    Args:
        page: The Playwright page
        element_id: The unique GWA ID of the element to annotate
    """
    await draw_bounding_boxes(page, [element_id])


async def clear_bounding_boxes(page: Page) -> None:
    """
    Clear any bounding boxes from the page.
    Note: This does not remove the data-gwa-id attributes.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        "() => { "
        + "Array.from(document.querySelectorAll('.GWA-rect, .GWA-label')).forEach(el => el.remove());"
        + " }"
    )


async def get_element_descriptions(
    page, element_simplified_htmls, output_dir
) -> Dict[int, Dict[str, str]]:
    """
    Get descriptions for all annotated elements on the page in parallel.

    Returns:
        A dictionary mapping element IDs to their descriptions and simplified HTML
    """

    # Process all elements in parallel
    tasks = []
    for element_id, simplified_html in element_simplified_htmls.items():
        await draw_bounding_box_around_element(page, element_id)
        page_screenshot_base64 = await take_screenshot(
            page,
        )
        await clear_bounding_boxes(page)
        tasks.append(
            (
                element_id,
                get_element_description(
                    page,
                    element_id,
                    simplified_html,
                    page_screenshot_base64,
                ),
            )
        )

    # Execute all tasks concurrently
    results = await asyncio.gather(*[task for _, task in tasks])

    # Map results to element IDs
    elements = {
        element_id: {
            "simplified_html": simplified_html,
            "description": result,
        }
        for (element_id, simplified_html), result in zip(tasks, results)
    }

    return elements


async def get_element_description(
    page: Page,
    element_id: str,
    simplified_html: str,
    page_screenshot: str,
    save_path: Optional[str] = None,
) -> str:
    """
    Get a description for a single element on the page.
    """
    element_screenshot = await take_element_screenshot(
        page,
        element_id,
        save_path=save_path,
    )

    if not element_screenshot:
        raise ValueError("No element screenshot")

    prompt = f"""Describe the element and it's purpose in the screenshot:

The first screenshot is the entire page with the element highlighted with a red bounding box.
The second screenshot is the element in question.

The element has the following HTML:
{simplified_html}


Output a very brief description of the element and it's purpose. Provide additional context about the element if necessary e.g. if there are multiple elements that look similar, describe the differences.

Example outputs:
'Add to Cart' button for the 13 inch MacBook Pro
Empty search bar at the top of the page
Link to the privacy policy
Button to select the color 'blue'.

Consider the context of the page when describing the element. For instance, if the element is a selector and has an outline around it, it is most likely selected.
"""

    user_message = llm_client.create_user_message_with_images(
        prompt, [page_screenshot, element_screenshot], "low"
    )
    response = await llm_client.make_call(
        [user_message], "gpt-4o", timeout=10, json_format=False
    )
    if not response.content:
        return simplified_html

    return response.content
