"""
Scroll actions for navigating up and down a page.
"""

import base64
import io
import json
import os
from datetime import datetime
from typing import Tuple

from PIL import Image
from playwright.async_api import Page

from agent.browser.actions.scroll import page_at_bottom, scroll_down, scroll_up
from agent.llm.client import LLMClient


class ScrollAgent:
    def __init__(self, content_to_find: str, page: Page, full_page_screenshot: str):
        self.content_to_find = content_to_find
        self.page = page
        self.full_page_screenshot = full_page_screenshot
        self.crop_height = 1600
        self.llm_client = LLMClient()

        image_data = base64.b64decode(full_page_screenshot)
        image = Image.open(io.BytesIO(image_data))

        self.crops = self.get_screenshot_crops(image, self.crop_height)
        self.num_crops = len(self.crops)

    async def run(self) -> str:
        found, description = await self.check_content_exists_on_page(
            self.content_to_find, self.crops
        )
        print(f"Found: {found}, Description: {description}")
        if not found:
            return f"Did not find anything on the page matching the description: {self.content_to_find}. If you think the content should be on the page, try a different description."

        initial_scroll_position = await self.page.evaluate(
            """() => {
                return (document.scrollingElement || document.body).scrollTop;
            }"""
        )
        content_visible = False
        while not content_visible and not await page_at_bottom(self.page):
            content_visible, vertical_position = await self.check_if_content_visible(
                description
            )
            if not content_visible:
                await scroll_down(self.page, 0.85)

        if content_visible:
            # extra logic to center content
            if vertical_position < 0.5:
                await scroll_up(self.page, abs(vertical_position - 0.5))
            else:
                await scroll_down(self.page, abs(vertical_position - 0.5))

            screenshot = await self.page.screenshot(full_page=False)
            # Save the screenshot to a file
            try:
                os.makedirs("found_content", exist_ok=True)
                screenshot_path = f"found_content/found_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                with open(screenshot_path, "wb") as f:
                    f.write(screenshot)
                print(f"Saved screenshot of found content to {screenshot_path}")
            except Exception as e:
                print(f"Error saving screenshot: {e}")

            return f"Found the content and scrolled to it. Content description: {description}"
        else:
            # Restore the scroll position
            await self.page.evaluate(
                f"""() => {{
                    (document.scrollingElement || document.body).scrollTop = {initial_scroll_position};
                }}"""
            )
            return f"Did not find the content on the page. Content description: {description}"

    def get_screenshot_crops(
        self,
        image: Image.Image,
        crop_height: int,
    ) -> list[str]:
        """Get a list of crops of the image"""
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

            # Convert back to base64
            buffered = io.BytesIO()
            crop.save(buffered, format="PNG")

            crop_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            crops.append(crop_base64)

        return crops

    async def check_content_exists_on_page(
        self, content_to_find: str, crops: list[str]
    ) -> Tuple[bool, str]:
        prompt = f"""You are a helpful assistant tasked with finding content on a page. You can see the page via the screenshots. The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page. It is possible that what you are looking for is not on the page.

Here is what you are looking for: {content_to_find}

Respond with a JSON object with the following fields:
{{
    "found": <true if you found the content, false otherwise>,
    "description": <a description of the content you found, including what it looks like. If you did not find the content, return "n/a">,
    "similar_content": <a description of some possibly similar content if you did not find the exact content. If no similar content is found or you found the exact content, return "n/a">,
}}"""

        user_message = self.llm_client.create_user_message_with_images(
            prompt, crops, "high"
        )
        response = await self.llm_client.make_call([user_message], "gpt-4o")

        if not response.content:
            return False, "Find tool failed to return a response"

        response_json = json.loads(response.content)
        print(f"Response: {response_json}")

        found = response_json["found"]
        description = response_json["description"]
        return found, description

    async def check_if_content_visible(self, description: str) -> Tuple[bool, float]:
        prompt = f"""You are a helpful assistant tasked with determining if some content is present in a screenshot.

Here is what you are looking for: {self.content_to_find}
{description}

Respond with a JSON object with the following fields:
{{  
    "found": <true if the content is present in the screenshot, false otherwise>,
    "vertical_position": <the vertical position of the content on screenshot as a float between 0 and 1, where 0 is the top of the screenshot and 1 is the bottom of the screenshot. If the content is not present, return -1>,
}}"""
        screenshot = await self.page.screenshot(full_page=False)
        screenshot_base64 = base64.b64encode(screenshot).decode("utf-8")

        user_message = self.llm_client.create_user_message_with_images(
            prompt, [screenshot_base64], "high"
        )
        response = await self.llm_client.make_call(
            [user_message], "o1", reasoning_effort="low"
        )
        if not response.content:
            return False, -1

        response_json = json.loads(response.content)
        print(f"Response: {response_json}")

        found = response_json["found"]
        vertical_position = float(response_json["vertical_position"])
        return found, vertical_position
