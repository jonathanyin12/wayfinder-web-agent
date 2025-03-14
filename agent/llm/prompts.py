import json
from typing import Dict, List

from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from agent.llm.client import LLMClient
from agent.models import AgentAction, BrowserTab


class PromptManager:
    def __init__(self, objective: str, llm_client: LLMClient):
        self.objective = objective
        self.llm_client = llm_client

    def get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        return f"""You are a helpful web browsing assistant.

Here is your ultimate objective: {self.objective}

POSSIBLE ACTIONS:
- click_element: click a specific element on the page
- type_text: type text into a text box on the page and optionally submit the text
- search_page: tool to search the entire page for specific information. This is the preferred way to find information on a page.
- scroll: scroll up or down on the page. Use this to find interactable elements (i.e. buttons, links, etc.) that are not currently visible in the current viewport.
- navigate: go back to the previous page or go forward to the next page
- go_to_url: go to a specific url
- switch_tab: switch to a different tab
- end: declare that you have completed the task
"""

    async def _get_planning_prompt(
        self,
        browser,
        last_action: AgentAction | None = None,
    ) -> str:
        page = browser.pages[browser.current_page_index]

        pixels_above, pixels_below = await page.get_pixels_above_below()
        page_position = get_formatted_page_position(pixels_above, pixels_below)
        interactable_elements = get_formatted_interactable_elements(
            pixels_above, pixels_below, page.element_descriptions
        )
        base_url = page.get_base_url()
        shortened_url = page.get_shortened_url()
        tabs = await get_formatted_tabs(browser)
        page_title = await page.page.title()

        """Returns the prompt template for planning the next action"""
        if not last_action:
            return f"""OPEN BROWSER TABS:
{tabs}

CURRENT PAGE STATE:
- Page title: {page_title}
- Site: {base_url}
- URL: {shortened_url}
- Page Position: {page_position}

Screenshot: current state of the page 

Interactable elements that are currently visible (element_id: element_html):
{interactable_elements}


TASK:
1. Provide a brief summary of the current page. Focus on new information.

2. Suggest a single next step given the current state of the page and the overall objective.

Respond with a JSON object with the following fields:
{{
    "page_summary": <Task 1>,
    "next_step": <Task 2>
}}"""
        return f"""OPEN BROWSER TABS:
{tabs}

CURRENT PAGE STATE:
- Page title: {page_title}
- Site: {base_url}
- URL: {shortened_url}
- Page Position: {page_position}

Screenshot 1: previous state of the page, before the last action was performed

Screenshot 2: current state of the page, after the last action was performed

Interactable elements that are currently visible (element_id: element_html):
{interactable_elements}


TASK:
1. Provide a brief summary of the current page (screenshot 2). Focus on new information.

2. Reason about whether the last action was successful or not.
- Carefully compare the before and after screenshots to verify whether the action was successful. Consider what UX changes are expected for the action you took.
- If an action is not successful, try to reason about what went wrong and what you can do differently. e.g. if you clicked on an element but it didn't change state, it may have already been selected or in the desired state. If you tried to scroll but the page didn't move, it may be the end of the page or the page is not scrollable.

3. Summarize what has been accomplished since the beginning.

4. Suggest a single next step given the current state of the page and the overall objective.
- If the objective is fully completed, the next step should be to end the task.

Respond with a JSON object with the following fields:
{{
    "page_summary": <Task 1>,
    "previous_action_evaluation": <Task 2>,
    "progress": <Task 3>,
    "next_step": <Task 4>
}}"""

    async def _get_action_prompt(
        self,
        browser,
        planning_response: Dict[str, str],
    ) -> str:
        """Returns the prompt template for planning the next action"""
        page = browser.pages[browser.current_page_index]
        pixels_above, pixels_below = await page.get_pixels_above_below()
        page_position = get_formatted_page_position(pixels_above, pixels_below)
        interactable_elements = get_formatted_interactable_elements(
            pixels_above, pixels_below, page.element_descriptions
        )
        base_url = page.get_base_url()
        shortened_url = page.get_shortened_url()
        page_title = await page.page.title()
        tabs = await get_formatted_tabs(browser)
        next_step = planning_response["next_step"]
        page_summary = planning_response["page_summary"]
        progress = planning_response.get(
            "progress", "You have not yet started the task."
        )

        return f"""OPEN BROWSER TABS:
{tabs}

CURRENT PAGE STATE:
- Page Summary: {page_summary}
- Page title: {page_title}
- Site: {base_url}
- URL: {shortened_url}
- Page Position: {page_position}

Screenshot 1: current state of the page 

Screenshot 2: the current page with bounding boxes drawn around interactable elements. The element IDs are the numbers in top-left of boxes.

Interactable elements that are currently visible (element_id: element_html):
{interactable_elements}

PROGRESS:
{progress}


TASK:
Select a single action that best completes the next step: 
"{next_step}"

Important Notes:
- If the next step requires multiple actions, choose only the first necessary action
- If you want to click on or type into an element that likely exists on the current page but is not currently visible, try to find it by scrolling
"""

    async def build_planning_message(
        self,
        browser,
        last_action: AgentAction | None = None,
    ) -> ChatCompletionUserMessageParam:
        planning_prompt = await self._get_planning_prompt(browser, last_action)

        page = browser.pages[browser.current_page_index]
        images = [
            page.previous_screenshot_base64,
            page.current_screenshot_base64,
        ]

        user_message = self.llm_client.create_user_message_with_images(
            planning_prompt, images, detail="high"
        )
        return user_message

    async def build_action_message(
        self,
        browser,
        planning_response: Dict[str, str],
    ) -> ChatCompletionUserMessageParam:
        action_prompt = await self._get_action_prompt(browser, planning_response)

        page = browser.pages[browser.current_page_index]
        images = [
            page.current_screenshot_base64,
            page.current_screenshot_annotated_base64,
        ]

        user_message = self.llm_client.create_user_message_with_images(
            action_prompt, images, detail="high"
        )
        return user_message


def get_formatted_interactable_elements(
    pixels_above, pixels_below, element_descriptions
) -> str:
    """
    Get a formatted string of interactable elements on the page.

    Args:
        page: The Playwright page
        element_descriptions: Dictionary of labeled HTML elements
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A formatted string representation of interactable elements
    """
    has_content_above = pixels_above > 0
    has_content_below = pixels_below > 0

    elements_text = json.dumps(element_descriptions, indent=4)
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
