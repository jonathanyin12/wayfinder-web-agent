import asyncio
from typing import Dict, Optional

from playwright.async_api import Page

from agent.browser.utils.annotation import (
    annotate_page_with_single_element,
    clear_annotations,
)
from agent.browser.utils.screenshot import take_element_screenshot, take_screenshot
from agent.llm.client import LLMClient

llm_client = LLMClient()


async def get_element_descriptions(
    page, label_selectors, label_simplified_htmls, output_dir
) -> Dict[int, str]:
    """
    Get descriptions for all annotated elements on the page in parallel.

    Returns:
        A dictionary mapping element IDs to their descriptions
    """

    # Process all elements in parallel
    tasks = []
    for element_id, selector in label_selectors.items():
        await annotate_page_with_single_element(page, selector)
        page_screenshot_base64 = await take_screenshot(
            page,
        )
        await clear_annotations(page)
        simplified_html = label_simplified_htmls[element_id]
        tasks.append(
            (
                element_id,
                get_element_description(
                    page,
                    selector,
                    simplified_html,
                    page_screenshot_base64,
                ),
            )
        )

    # Execute all tasks concurrently
    results = await asyncio.gather(*[task for _, task in tasks])

    # Map results to element IDs
    element_descriptions = {
        element_id: result for (element_id, _), result in zip(tasks, results)
    }

    return element_descriptions


async def get_element_description(
    page: Page,
    selector: str,
    simplified_html: str,
    page_screenshot: str,
    save_path: Optional[str] = None,
) -> str:
    """
    Get a description for a single element on the page.
    """
    element_screenshot = await take_element_screenshot(
        page,
        selector,
        save_path=save_path,
    )

    if not element_screenshot:
        raise ValueError("No element screenshot")

    prompt = f"""Describe the element and it's purpose in the screenshot:

The first screenshot is the entire page with the element highlighted with a red bounding box.
The second screenshot is the element in question.

The element is described by the following HTML:
{simplified_html}


Output a very brief description of the element and it's purpose. Provide additional context about the element if necessary e.g. if there are multiple elements that look similar, describe the differences.

Example outputs:
'Add to Cart' button for the 13 inch MacBook Pro
Empty search bar at the top of the page
Link to the privacy policy
Button to select the color 'blue'. It is currently selected.

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
