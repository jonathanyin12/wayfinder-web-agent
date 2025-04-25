"""
Annotation actions for labeling and identifying interactive elements on web pages.
"""

import asyncio
import base64
import io
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw
from playwright.async_api import Page

from web_agent.browser.utils.dom_utils.load_js_file import load_js_file
from web_agent.browser.utils.screenshot import take_element_screenshot, take_screenshot
from web_agent.llm.client import LLMClient


async def preprocess_page(
    page: Page, output_dir: str, llm_client: LLMClient
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
    # start_time = time.time()
    # elements = await get_element_descriptions(
    #     page, element_simplified_htmls, screenshot_base64, output_dir, llm_client
    # )
    # end_time = time.time()
    # print(
    #     f"Time taken to get {len(elements)} element descriptions: {end_time - start_time} seconds"
    # )

    elements = {
        element_id: {
            "simplified_html": element_simplified_htmls[element_id],
            # "description": element_simplified_htmls[element_id],
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
    element_count = 0  # Track elements across all iframes

    for element in iframe_elements:
        # Check if the iframe is visible before processing its contents
        try:
            # Check 1: Playwright's built-in visibility
            is_visible = await element.is_visible()
            if not is_visible:
                # Optional: Log why it's skipped
                # print(f"Skipping non-visible iframe (is_visible=False): {await element.get_attribute('src')}")
                continue

            # Check 2: Bounding box check for zero size
            bounding_box = await element.bounding_box()
            if (
                not bounding_box
                or bounding_box["width"] <= 0
                or bounding_box["height"] <= 0
            ):
                # Optional: Log why it's skipped
                # print(f"Skipping iframe with zero-size bounding box: {await element.get_attribute('src')}")
                continue

            # Check 3: Coordinate check for being outside viewport
            viewport_size = page.viewport_size
            if not viewport_size:
                # Fallback or skip if viewport size is unavailable
                print(
                    "Warning: Viewport size not available, skipping coordinate check for iframe."
                )
            elif (
                bounding_box["x"] + bounding_box["width"] < 0  # Completely left
                or bounding_box["y"] + bounding_box["height"] < 0  # Completely above
                or bounding_box["x"] > viewport_size["width"]  # Completely right
                or bounding_box["y"] > viewport_size["height"]  # Completely below
            ):
                # Optional: Log why it's skipped
                # print(f"Skipping iframe outside of viewport: {await element.get_attribute('src')}")
                continue

            # Check 4: Explicit check for computed display/visibility styles
            styles = await element.evaluate(
                "el => JSON.stringify(window.getComputedStyle(el))"
            )
            computed_style = json.loads(styles)
            if (
                computed_style.get("display") == "none"
                or computed_style.get("visibility") == "hidden"
            ):
                # Optional: Log why it's skipped
                # print(f"Skipping iframe with computed style hidden: {await element.get_attribute('src')}")
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

            # --- Start HTML Simplification ---
            tag_name = await elem.evaluate("el => el.tagName.toLowerCase()")
            simplified_html = f"<{tag_name}"

            attrs_to_check = [
                # Standard Attributes
                "name",
                "role",
                "type",
                "value",
                "placeholder",
                "title",
                "alt",
                "href",
                # Boolean State Attributes
                "checked",
                "selected",
                "disabled",
                "readonly",
                # ARIA Attributes
                "aria-label",
                "aria-checked",
                "aria-selected",
                "aria-expanded",
                "aria-pressed",
                "aria-disabled",
                "aria-current",
                "aria-haspopup",
            ]
            boolean_attrs = [
                "checked",
                "selected",
                "disabled",
                "readonly",
                "aria-checked",
                "aria-selected",
                "aria-expanded",
                "aria-pressed",
                "aria-disabled",
                "aria-current",
            ]

            for attr in attrs_to_check:
                attr_value = await elem.get_attribute(attr)
                if attr_value is not None:
                    # Represent boolean attributes consistently
                    if attr in boolean_attrs and attr_value == "":
                        attr_value = "true"

                    # Avoid adding empty attributes unless meaningful (like value="")
                    if attr_value != "" or attr in [
                        "value",
                        "alt",
                        "placeholder",
                        "title",
                        "href",
                    ]:
                        # Truncate long attribute values
                        if len(attr_value) > 50:
                            attr_value = attr_value[:47] + "..."
                        simplified_html += f' {attr}="{attr_value}"'

            # Get inner text, trying common fallbacks for inputs
            inner_text = await elem.inner_text()
            if tag_name == "input" and not inner_text:
                value = await elem.get_attribute("value")
                placeholder = await elem.get_attribute("placeholder")
                aria_label = await elem.get_attribute("aria-label")
                title = await elem.get_attribute("title")
                # Use the first available text source as a fallback
                inner_text = value or placeholder or aria_label or title or ""

            # Clean and add inner text
            inner_text = " ".join(inner_text.split()) if inner_text else ""
            # Note: JS version doesn't truncate inner text, only attributes.
            simplified_html += f">{inner_text}</{tag_name}>"
            # --- End HTML Simplification ---

            # Add a unique identifier to track this iframe element
            # Using starting_index + a unique counter for all iframe elements
            iframe_element_id = starting_index + element_count
            element_count += 1

            await elem.evaluate(
                f"el => el.setAttribute('data-gwa-id', 'gwa-element-{iframe_element_id}')"
            )
            # Use the simplified HTML
            iframes_element_simplified_htmls[iframe_element_id] = simplified_html

            box = await elem.bounding_box()
            if not box:
                continue
            # Draw an overlay around the iframe element
            await page.evaluate(
                """([x, y, width, height, elementId]) => {
                    // Create overlay with absolute positioning relative to the main document
                    const overlay = document.createElement("div");
                    overlay.className = "GWA-rect";
                    overlay.style.position = "fixed";
                    overlay.style.left = x + "px";
                    overlay.style.top = y + "px";
                    overlay.style.width = width + "px";
                    overlay.style.height = height + "px";
                    overlay.style.border = "2px solid brown";
                    overlay.style.backgroundColor = "rgba(165, 42, 42, 0.1)";
                    overlay.style.zIndex = "2147483647";
                    overlay.style.pointerEvents = "none";

                    // Add a label with the element ID
                    const label = document.createElement("span");
                    label.className = "GWA-label";
                    label.textContent = elementId;
                    label.style.position = "fixed";
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
    page, element_simplified_htmls, screenshot_base64, output_dir, llm_client
) -> Dict[int, Dict[str, str]]:
    """
    Get descriptions for all annotated elements on the page in parallel.

    Returns:
        A dictionary mapping element IDs to their descriptions and simplified HTML
    """

    # Process all elements in parallel with a semaphore to limit concurrent calls
    tasks = []
    # Limit to 20 concurrent calls
    semaphore = asyncio.Semaphore(20)

    async def get_element_description_with_semaphore(
        page, element_id, simplified_html, screenshot_base64, output_dir, llm_client
    ):
        async with semaphore:
            return await get_element_description(
                page,
                element_id,
                simplified_html,
                screenshot_base64,
                output_dir,
                llm_client,
            )

    for element_id, simplified_html in element_simplified_htmls.items():
        # Create the task with semaphore control
        task = get_element_description_with_semaphore(
            page,
            element_id,
            simplified_html,
            screenshot_base64,
            output_dir,
            llm_client,
        )
        tasks.append((element_id, task))

    # Execute all tasks concurrently with semaphore limiting to 20 at a time
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
    screenshot_base64: str,
    output_dir: str,
    llm_client: LLMClient,
) -> str:
    """
    Get a description for a single element on the page.
    """

    # Get the element bounding box coordinates
    selector = f'[data-gwa-id="gwa-element-{element_id}"]'
    element_handle = await page.query_selector(selector)
    if not element_handle:
        return "Element not found"

    bounding_box = await element_handle.bounding_box()
    if not bounding_box:
        return "Element has no bounding box"

    # Manually draw the bounding box on the screenshot using PIL
    image_data = base64.b64decode(screenshot_base64)
    image = Image.open(io.BytesIO(image_data))
    draw = ImageDraw.Draw(image)
    # Add a small buffer around the bounding box for better visibility
    buffer = 10
    draw.rectangle(
        [
            max(0, bounding_box["x"] - buffer),
            max(0, bounding_box["y"] - buffer),
            bounding_box["x"] + bounding_box["width"] + buffer,
            bounding_box["y"] + bounding_box["height"] + buffer,
        ],
        outline="red",
        width=5,
    )
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")

    page_screenshot_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    prompt = f"""Task: Describe the function of the UI element in the screenshot.

The first screenshot is the entire page with the element outlined with a red bounding box.

The element has the following HTML:
{simplified_html}


Provide additional context about the element if necessary e.g. if there are multiple identical elements, say what the element is associated with.


Output your response in JSON format:
{{
  "description": "string | a few words describing the element and its function. Include any disambiguating information if there are multiple elements that look similar.",
}}
"""

    user_message = llm_client.create_user_message_with_images(
        prompt, [page_screenshot_base64], "high"
    )
    response = await llm_client.make_call(
        [user_message],
        "gpt-4.1-mini",
        timeout=30,
        json_format=True,
    )

    if not response.content:
        return simplified_html

    json_response = json.loads(response.content)

    output = f"{json_response['description']} "

    return output


async def get_page_overview(
    page: Page, full_page_screenshot_crops: List[str], llm_client: LLMClient
) -> Tuple[str, str]:
    """
    Get a brief overview of the page.
    """
    # Convert base64 screenshot to PIL Image

    page_title = await page.title()

    prompt = f"""Tasks:
1. Describe the main purpose of the page

2. Provide a detailed overview of the key sections of the page. For each section, include a title, a brief description of the section, and important interactive elements (e.g. buttons, links, form fields, etc.). Order the sections from top to bottom as a numbered list.


Page Title: {page_title}
Page URL: {page.url}

The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page.

Output your response in JSON format.
{{
    "summary": <Answer to task 1>,
    "detailed_breakdown": <Answer to task 2 in markdown format>,
}}"""

    user_message = llm_client.create_user_message_with_images(
        prompt, full_page_screenshot_crops, "high"
    )
    response = await llm_client.make_call(
        [user_message], "gpt-4.1-mini", json_format=True
    )

    if not response.content:
        raise ValueError("No response from the LLM")

    response_json = json.loads(response.content)
    return response_json["summary"], response_json["detailed_breakdown"]
