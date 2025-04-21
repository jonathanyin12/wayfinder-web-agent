"""
Scroll actions for navigating up and down a page.
"""

import base64
import io
import json
from typing import List

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Page

from agent.browser.core.page import browser_action
from agent.llm.client import LLMClient


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


async def _find_content_on_page(
    content_to_find: str, crops: list[str], llm_client: LLMClient
) -> dict:
    """Find the content on the page using LLM and return the response."""

    prompt = f"""You are a helpful assistant tasked with finding content on a page. You can see the page via the screenshots. The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page. The screenshots are indexed from 0 to {len(crops) - 1}, with index 0 being the first screenshot and {len(crops) - 1} being the last screenshot. The screenshot index is also written in red in the bottom right corner of each screenshot.

Here is what you are looking for: {content_to_find}

Guidelines:
- It is possible that what you are looking for is not on the page.
- If you found multiple possible matches, respond with the one that you feel is the most likely to be the one the user is looking for.
- If you can't find the exact content, but there exists a similar matching content on the page, tell the user in your response. "found" should still be false in this case.

In your response, don't mention what screenshot you found the content in since the page will be automatically scrolled to the appropriate position.

Respond with a JSON object with the following fields:
{{
    "found": <true if you found the content, false otherwise>,
    "response": <"your response to the user">,
    "screenshot_index": <the index of the screenshot that contains the content, if found, otherwise -1.>,
    "location": <the location of the content on the screenshot, if found, otherwise n/a.>,
}}"""

    user_message = llm_client.create_user_message_with_images(prompt, crops, "high")
    response = await llm_client.make_call([user_message], "gpt-4.1")

    if not response.content:
        # Return a default response indicating failure
        return {
            "found": False,
            "response": "Find tool failed to return a response",
            "screenshot_index": -1,
            "location": "n/a",
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
            "location": "n/a",
        }


async def _get_vertical_position(
    content_to_find: str,
    location: str,
    screenshot: str,
    llm_client: LLMClient,
    use_location: bool = False,
) -> float:
    """Get the vertical position of the content on the page"""
    if use_location:
        prompt = f"""You are a helpful assistant tasked with determining the vertical position of content on a screenshot. The vertical position of the content on the screenshot can be represented as a float between 0 and 1, where 0 means the content is at the top of the screenshot, 0.5 means the content is at the middle of the screenshot, and 1 means the content is at the bottom of the screenshot. If you can't find the content, make an educated guess based on the description of the location of the content.

Here is the content you are looking for: {content_to_find}

Description of the location of the content: {location}

Respond with a JSON object with the following field:
{{
    "vertical_position": <a float between 0 and 1>,
}}"""
    else:
        prompt = f"""You are a helpful assistant tasked with determining the vertical position of content on a screenshot. The vertical position of the content on the screenshot can be represented as a float between 0 and 1, where 0 means the content is at the top of the screenshot, 0.5 means the content is at the middle of the screenshot, and 1 means the content is at the bottom of the screenshot. If you can't find the content, set the vertical position to -1.

Here is the content you are looking for: {content_to_find}

Respond with a JSON object with the following field:
{{
    "vertical_position": <a float between 0 and 1, or -1 if you can't find the content.>,
}}"""

    user_message = llm_client.create_user_message_with_images(
        prompt, [screenshot], "high"
    )
    response = await llm_client.make_call([user_message], "o1")

    if not response.content:
        print("Get vertical position tool failed to return a response")
        return -1

    response_json = json.loads(response.content)
    vertical_position = float(response_json["vertical_position"])
    if vertical_position == -1:
        print(
            "vertical position is -1, getting vertical position from location, which may be inaccurate"
        )
        vertical_position = await _get_vertical_position(
            content_to_find, location, screenshot, llm_client, use_location=True
        )
    return vertical_position


@browser_action
async def scroll(page: Page, direction: str, amount: float = 0.75):
    """Scroll the page in the given direction by the given amount"""
    if direction == "down":
        await scroll_down(page, amount)
    elif direction == "up":
        await scroll_up(page, amount)


@browser_action
async def find(
    page: Page,
    content_to_find: str,
    full_page_screenshot_crops: List[str],
    llm_client: LLMClient,
    page_height: int,
):
    """Scroll to the content on the page"""
    crops = label_screenshots(full_page_screenshot_crops)[:-20]
    crop_height = 1600

    find_result = await _find_content_on_page(content_to_find, crops, llm_client)

    found = find_result["found"]
    output = find_result["response"]
    screenshot_index = find_result["screenshot_index"]
    location = find_result["location"]

    # If content was found, scroll to the appropriate position in the page
    if found and screenshot_index >= 0 and screenshot_index < len(crops):
        vertical_position = await _get_vertical_position(
            content_to_find, location, crops[screenshot_index], llm_client
        )
        scroll_position = max(
            0,
            min(
                (screenshot_index + vertical_position - 0.5) * crop_height,
                page_height - 1600,
            ),
        )

        await page.evaluate(f"window.scrollTo(0, {scroll_position});")

        current_scroll_position = await page.evaluate(
            """() => {
                return (document.scrollingElement || document.body).scrollTop;
            }"""
        )
        if abs(scroll_position - current_scroll_position) > 100:
            # This helps with pages like https://pillow.readthedocs.io/en/stable/reference/ImageFont.html
            print(
                f"Scroll position mismatch: {scroll_position} != {current_scroll_position}, falling back to iterative scrolling"
            )
            # Move mouse to the center of the screen to ensure focus
            await page.mouse.move(600, 800)
            while current_scroll_position < scroll_position:
                await scroll_down(page, 0.2)
                await page.wait_for_timeout(500)  # Wait for 100 milliseconds
                current_scroll_position = await page.evaluate(
                    """() => {
                        return (document.scrollingElement || document.body).scrollTop;
                    }"""
                )

    return output


def label_screenshots(
    crops: List[str],
) -> list[str]:
    """
    Label a list of base64-encoded image crops with indices in the bottom right corner

    Args:
        crops: List of base64-encoded PNG images to label

    Returns:
        List of base64-encoded PNG images with index labels
    """
    labeled_crops = []

    for i, crop_base64 in enumerate(crops):
        # Decode base64 to image
        image_data = base64.b64decode(crop_base64)
        image = Image.open(io.BytesIO(image_data))

        # Add label to the crop
        draw = ImageDraw.Draw(image)
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
            (image.width - 100 * len(str(i)), image.height - 125),
            str(i),
            fill="red",
            font=font,
            stroke_width=10,
            stroke_fill="white",
        )

        # Convert back to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        labeled_crop_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        labeled_crops.append(labeled_crop_base64)

    return labeled_crops
