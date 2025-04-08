"""
Scroll actions for navigating up and down a page.
"""

import base64
import io
import json

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Page

from agent.browser.core.page import browser_action
from agent.llm.client import LLMClient

llm_client = LLMClient()


async def scroll_down(page: Page, amount: float = 0.75):
    """
    Scroll down the page by approximately a fraction of the viewport height.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        """(amount) => {
            (document.scrollingElement || document.body).scrollTop = 
                (document.scrollingElement || document.body).scrollTop + (window.innerHeight * amount);
        }""",
        amount,
    )


async def scroll_up(page: Page, amount: float = 0.75):
    """
    Scroll up the page by approximately a fraction of the viewport height.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        """(amount) => {
            (document.scrollingElement || document.body).scrollTop = 
                (document.scrollingElement || document.body).scrollTop - (window.innerHeight * amount);
        }""",
        amount,
    )


async def _find_content_on_page(content_to_find: str, crops: list[str]) -> dict:
    """Find the content on the page using LLM and return the response."""

    prompt = f"""You are a helpful assistant tasked with finding content on a page. You can see the page via the screenshots. The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page. The screenshots are indexed from 0 to {len(crops) - 1}, with index 0 being the first screenshot and {len(crops) - 1} being the last screenshot. The screenshot index is also written in the bottom right corner of each screenshot.

Here is what you are looking for: {content_to_find}

Guidelines:
- It is possible that what you are looking for is not on the page.
- If you found multiple possible matches, respond with the one that you feel is the most likely to be the one the user is looking for.

In your response, don't mention what screenshot you found the content in since the page will be scrolled to the appropriate position.

Respond with a JSON object with the following fields:
{{
    "found": <true if you found the content, false otherwise>,
    "response": <"your response to the user">,
    "screenshot_index": <the index of the screenshot that contains the content, if found, otherwise -1>,
}}"""

    user_message = llm_client.create_user_message_with_images(prompt, crops, "high")
    response = await llm_client.make_call([user_message], "gpt-4o")

    if not response.content:
        # Return a default response indicating failure
        return {
            "found": False,
            "response": "Find tool failed to return a response",
            "screenshot_index": -1,
        }

    try:
        response_json = json.loads(response.content)
        return response_json
    except json.JSONDecodeError:
        # Handle cases where the response is not valid JSON
        print(f"Error decoding JSON from LLM response: {response.content}")
        return {
            "found": False,
            "response": "Find tool returned invalid JSON",
            "screenshot_index": -1,
        }


async def _get_vertical_position(content_to_find: str, screenshot: str) -> float:
    """Get the vertical position of the content on the page"""
    prompt = f"""You are a helpful assistant tasked with determining the vertical position of content on a screenshot. The vertical position of the content on the screenshot can be represented as a float between 0 and 1, where 0 means the content is at the top of the screenshot, 0.5 means the content is at the exact middle of the screenshot, and 1 means the content is at the bottom of the screenshot.

Here is the content you are looking for: {content_to_find}

Respond with a JSON object with the following field:
{{
    "vertical_position": <a float between 0 and 1. If the content is not present, return -1>,
}}"""

    user_message = llm_client.create_user_message_with_images(
        prompt, [screenshot], "high"
    )
    response = await llm_client.make_call([user_message], "gpt-4o")

    if not response.content:
        return -1

    response_json = json.loads(response.content)
    return float(response_json["vertical_position"])


@browser_action
async def scroll(page: Page, content_to_find: str, full_page_screenshot: str):
    """Scroll to the content on the page"""
    image_data = base64.b64decode(full_page_screenshot)
    image = Image.open(io.BytesIO(image_data))
    crop_height = 1600
    crops = get_screenshot_crops_with_labels(image, crop_height)
    find_result = await _find_content_on_page(content_to_find, crops)

    found = find_result["found"]
    output = find_result["response"]
    screenshot_index = find_result["screenshot_index"]

    # If content was found, scroll to the appropriate position in the page
    if found and screenshot_index >= 0 and screenshot_index < len(crops):
        vertical_position = await _get_vertical_position(
            content_to_find, crops[screenshot_index]
        )
        if 0.0 <= vertical_position <= 1.0:
            scroll_position = (screenshot_index + vertical_position - 0.5) * crop_height
        else:
            scroll_position = screenshot_index * crop_height
        await page.evaluate(f"window.scrollTo(0, {scroll_position});")
        print(
            f"Screenshot index: {screenshot_index}, vertical position: {vertical_position}"
        )
    return output


def get_screenshot_crops_with_labels(
    image: Image.Image,
    crop_height: int,
) -> list[str]:
    """
    Get a list of crops of the image with labeled indices in the bottom right corner

    Args:
        image: The PIL Image to crop
        crop_height: Height of each crop in pixels

    Returns:
        List of base64-encoded PNG images with index labels
    """
    # Get dimensions
    width, height = image.size

    # Calculate number of crops needed
    num_crops = (height + crop_height - 1) // crop_height  # Ceiling division

    # Create crops
    crops = []
    for i in range(num_crops):
        top = i * crop_height
        bottom = min(top + crop_height, height)

        # Crop the image
        crop = image.crop((0, top, width, bottom))

        # Add label to the crop
        draw = ImageDraw.Draw(crop)
        font_size = 100
        try:
            font = ImageFont.truetype("Arial.ttf", font_size)
        except (IOError, ImportError) as e:
            # Fallback if font not available or ImageFont can't be imported
            print(
                f"Font not available or ImageFont could not be imported, falling back to default: {e}"
            )
            font = None
        draw.text(
            (crop.width - 100 * len(str(i)), crop.height - 125),
            str(i),
            fill="red",
            font=font,
            stroke_width=10,
            stroke_fill="white",
        )

        # Convert to base64
        buffered = io.BytesIO()
        crop.save(buffered, format="PNG")
        crop_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        crops.append(crop_base64)

    return crops
