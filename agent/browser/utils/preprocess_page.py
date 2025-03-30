"""
Annotation actions for labeling and identifying interactive elements on web pages.
"""

import asyncio
import base64
import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image
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
    starting_index = len(element_simplified_htmls)
    # Find iframe elements and their interactive elements
    iframe_elements = await find_iframe_interactive_elements(page, starting_index)

    # Merge iframe elements with main page elements
    element_simplified_htmls.update(iframe_elements)

    bounding_box_screenshot_base64 = await take_screenshot(
        page,
        save_path=f"{output_dir}/bounding_box_screenshots/{timestamp}.png",
    )
    await clear_bounding_boxes(page)
    # elements = await get_element_descriptions(
    #     page, element_simplified_htmls, output_dir
    # )
    elements = {
        element_id: {
            "simplified_html": element_simplified_htmls[element_id],
            "description": element_simplified_htmls[element_id],
        }
        for element_id in element_simplified_htmls
    }

    return screenshot_base64, bounding_box_screenshot_base64, elements


async def find_iframe_interactive_elements(
    page: Page, starting_index: int
) -> Dict[int, str]:
    """
    Find and identify interactive elements within iframes on the page.
    """
    iframe_locator = page.locator("iframe")
    iframe_elements = await iframe_locator.element_handles()
    iframes_element_simplified_htmls = {}
    for element in iframe_elements:
        # Check if the iframe is visible before processing its contents
        try:
            is_visible = await element.is_visible()
            if not is_visible:
                continue
        except Exception as e:
            print(f"Error checking iframe visibility: {e}")
            continue

        # Get the Frame object from the iframe element handle
        frame = await element.content_frame()
        if not frame:
            continue

        interactive_locator = frame.locator("a, button, input, select, textarea")
        count = await interactive_locator.count()

        for i in range(count):
            elem = interactive_locator.nth(i)
            if not await elem.is_visible():
                continue

            text = await elem.text_content() or await elem.get_attribute("value") or ""
            # Get the HTML of the element
            tag_name = await elem.evaluate("el => el.tagName.toLowerCase()")
            html = await elem.evaluate("el => el.outerHTML")

            # For input elements, we might want to get additional attributes
            if tag_name == "input":
                input_type = await elem.get_attribute("type") or ""
                value = await elem.get_attribute("value") or ""
                placeholder = await elem.get_attribute("placeholder") or ""
                html = f"<{tag_name} type='{input_type}' value='{value}' placeholder='{placeholder}'>{text}</{tag_name}>"

            # Add a unique identifier to track this iframe element
            # Using a high number range (1000000+) to avoid conflicts with main page elements
            iframe_element_id = starting_index + i
            await elem.evaluate(
                f"el => el.setAttribute('data-gwa-id', 'gwa-element-{iframe_element_id}')"
            )
            iframes_element_simplified_htmls[iframe_element_id] = html

            box = await elem.bounding_box()
            if not box:
                continue
            # Draw an overlay around the iframe element
            await page.evaluate(
                """([x, y, width, height, elementId]) => {
                    // Create overlay with absolute positioning relative to the main document
                    const overlay = document.createElement("div");
                    overlay.className = "GWA-rect";
                    overlay.style.position = "absolute";
                    overlay.style.left = x + "px";
                    overlay.style.top = y + "px";
                    overlay.style.width = width + "px";
                    overlay.style.height = height + "px";
                    overlay.style.border = "2px solid brown";
                    overlay.style.backgroundColor = "rgba(165, 42, 42, 0.1)";
                    overlay.style.zIndex = "2147483647"; // Maximum z-index to ensure visibility
                    overlay.style.pointerEvents = "none"; // Make sure it doesn't block interactions

                    // Add a label with the element ID
                    const label = document.createElement("span");
                    label.className = "GWA-label";
                    label.textContent = elementId;
                    label.style.position = "absolute";
                    label.style.top = y + "px";
                    label.style.left = x + "px";
                    label.style.backgroundColor = "brown";
                    label.style.color = "white";
                    label.style.fontWeight = "bold";
                    label.style.fontSize = "14px";
                    label.style.padding = "1px";
                    label.style.zIndex = "2147483647";
                                    
                    
                    // Append the overlay and label to the main document body
                    document.body.appendChild(overlay);
                    document.body.appendChild(label);
                }""",
                [
                    box["x"],
                    box["y"],
                    box["width"],
                    box["height"],
                    iframe_element_id,
                ],
            )
    return iframes_element_simplified_htmls


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

        # Create the task
        task = get_element_description(
            page,
            element_id,
            simplified_html,
            page_screenshot_base64,
        )
        tasks.append((element_id, task))

    # Execute all tasks concurrently
    results = await asyncio.gather(*[task for _, task in tasks])

    # Map results to element IDs
    elements = {}
    for (element_id, _), result in zip(tasks, results):
        elements[element_id] = {
            "simplified_html": element_simplified_htmls[element_id],
            "description": result,
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


async def get_page_overview(page: Page, full_page_screenshot: str) -> str:
    """
    Get a brief overview of the page.
    """

    # Convert base64 screenshot to PIL Image
    image_data = base64.b64decode(full_page_screenshot)
    image = Image.open(io.BytesIO(image_data))

    # Get dimensions
    width, height = image.size

    # Define the crop height
    crop_height = 1600

    # Calculate number of crops needed
    num_crops = (height + crop_height - 1) // crop_height  # Ceiling division

    num_crops = min(num_crops, 10)
    # Create crops
    crops = []
    for i in range(num_crops):
        top = i * crop_height
        bottom = min(top + crop_height, height)

        # Crop the image
        crop = image.crop((0, top, width, bottom))

        # Convert back to base64
        buffered = io.BytesIO()
        crop.save(buffered, format="PNG")
        crop_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        crops.append(crop_base64)

    page_title = await page.title()

    prompt = f"""Tasks:
1. Describe the main purpose of the page

2. Provide a detailed overview of the key sections of the page. For each section, include a title, a brief description of the section, and important interactive elements (e.g. buttons, links, form fields, etc.). Order the sections from top to bottom as a numbered list.


Page Title: {page_title}
Page URL: {page.url}

The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page.
"""

    user_message = llm_client.create_user_message_with_images(prompt, crops, "high")
    response = await llm_client.make_call([user_message], "gpt-4o", json_format=False)

    if not response.content:
        return "No response from the LLM"

    return response.content
