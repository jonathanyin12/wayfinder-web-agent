"""
Scroll actions for navigating up and down a page.
"""

import base64
import io
import json

from PIL import Image
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


# @browser_action
# async def scroll(page: Page, direction: str, amount: float = 0.75):
#     """
#     Scroll the page in a specified direction.

#     Args:
#         page: The Playwright page
#         direction: The direction to scroll ('up' or 'down')
#         amount: The fraction of the page height to scroll. 0.75 is a good default. If you only want to scroll a little, use 0.4.
#     """
#     if direction == "down":
#         await scroll_down(page, amount)
#     elif direction == "up":
#         await scroll_up(page, amount)


@browser_action
async def scroll(content_to_find: str, page: Page, full_page_screenshot: str) -> str:
    """Scroll to find content on the page"""

    # Convert base64 screenshot to PIL Image
    image_data = base64.b64decode(full_page_screenshot)
    image = Image.open(io.BytesIO(image_data))

    # Get dimensions
    width, height = image.size

    # Define the crop height
    crop_height = 1600

    # Calculate number of crops needed
    num_crops = (height + crop_height - 1) // crop_height  # Ceiling division
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

    prompt = f"""You are a helpful assistant tasked with finding content on a page. You can see the page via the screenshots. The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page.

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
}}
"""

    user_message = llm_client.create_user_message_with_images(prompt, crops, "high")
    response = await llm_client.make_call([user_message], "gpt-4o")

    if not response.content:
        return "Find tool failed to return a response"

    response_json = json.loads(response.content)

    # If content was found, scroll to the appropriate position in the page
    if response_json["screenshot_index"] != -1:
        # Calculate the scroll position based on the screenshot index
        # Each screenshot represents crop_height pixels
        scroll_position = response_json["screenshot_index"] * crop_height

        # Scroll to that position in the page
        await page.evaluate(f"window.scrollTo(0, {scroll_position});")

    return response_json["response"]
