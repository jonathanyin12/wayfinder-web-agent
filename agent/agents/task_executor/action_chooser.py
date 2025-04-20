import json
from typing import List

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from agent.agents.utils.prompt_formatting import (
    get_formatted_interactable_elements,
    get_formatted_page_position,
    get_formatted_tabs,
)
from agent.browser import AgentBrowser
from agent.browser.core.tools import TOOLS
from agent.llm import LLMClient
from agent.models import AgentAction


async def get_action_choice_prompt(browser: AgentBrowser, goal: str) -> str:
    """Returns the prompt template for planning the next action"""
    page = browser.current_page
    pixels_above, pixels_below = await page.get_pixels_above_below()
    page_position = get_formatted_page_position(pixels_above, pixels_below)
    page_summary = page.page_summary
    page_breakdown = page.page_breakdown
    interactable_elements = get_formatted_interactable_elements(
        pixels_above, pixels_below, page.elements
    )
    tabs = await get_formatted_tabs(browser)
    return f"""OPEN BROWSER TABS:
{tabs}

PAGE DETAILS:
{page_position}

- Summary:
{page_summary}


- Detailed breakdown:
{page_breakdown}


About the screenshot:
- It shows the current visible portion of the page with bounding boxes drawn around interactable elements.
- The element IDs are the numbers in top-left of boxes.


CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK: Choose the next action that helps you towards the current goal.

Goal: {goal}

Guidelines:
- DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING. Try an alternative strategy.
- Consider the feedback from previous actions if they failed.

Rules:
- Always use the extract action if you need to extract specific information from the page (recipe, top comment, title, etc.), even if you can see the information on the page.
- If you need to find a specific element on the page to interact with (e.g. a button, link, etc.), use the scroll_to_content action instead of the scroll action. Only use the scroll action if you need to view more of the page.
- When performing a search via a search bar, use a more general query if the current query is not working.
- For date inputs, type the desired date instead of using the date picker.
- If there is a dropdown menu, select an option before proceeding.
"""


class ActionChooser:
    def __init__(self, llm_client: LLMClient, browser: AgentBrowser, model: str):
        self.llm_client = llm_client
        self.browser = browser
        self.model = model

    async def choose_next_action(
        self,
        message_history: List[ChatCompletionMessageParam],
        goal: str,
    ) -> AgentAction:
        """Choose the next action to take based on the goal and feedback."""

        action_choice_prompt = await get_action_choice_prompt(self.browser, goal)
        images = [self.browser.current_page.bounding_box_screenshot]
        user_message = self.llm_client.create_user_message_with_images(
            action_choice_prompt, images, detail="high"
        )
        tool_call_message = await self.llm_client.make_call(
            [
                *message_history,
                user_message,
            ],
            self.model,
            tools=TOOLS,
        )
        if not tool_call_message.tool_calls:
            # TODO: Handle this case more gracefully, maybe ask user or retry?
            raise ValueError("No tool calls received from LLM in choose_next_action")

        tool_call = tool_call_message.tool_calls[0]

        args = json.loads(tool_call.function.arguments)

        action = AgentAction(
            name=tool_call.function.name,
            element=self.browser.current_page.elements.get(
                args.get("element_id", -1), {}
            ),
            args=args,
            tool_call=tool_call,
        )
        print(action)

        return action
