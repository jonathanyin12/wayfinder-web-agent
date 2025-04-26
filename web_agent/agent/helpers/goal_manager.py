import json
from typing import List, Tuple

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from web_agent.agent.utils.prompt_formatting import (
    get_formatted_interactable_elements,
    get_formatted_page_position,
    get_formatted_tabs,
)
from web_agent.browser import AgentBrowser
from web_agent.llm import LLMClient


class GoalManager:
    def __init__(self, llm_client: LLMClient, browser: AgentBrowser, model: str):
        self.llm_client = llm_client
        self.browser = browser
        self.model = model

    async def determine_next_goal(
        self, message_history: List[ChatCompletionMessageParam]
    ) -> str:
        """Determines the next goal based on the current state and history."""
        next_goal_prompt = await get_next_goal_prompt(self.browser)

        full_page_screenshot_crops = (
            self.browser.current_page.get_full_page_screenshot_crops()
        )
        user_message = self.llm_client.create_user_message_with_images(
            next_goal_prompt,
            full_page_screenshot_crops,
            detail="high",
        )

        response = await self.llm_client.make_call(
            [
                *message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )

        if not response.content:
            raise ValueError(
                "No response content received from LLM in determine_next_goal"
            )

        response_json = json.loads(response.content)
        next_goal = response_json["next_goal"]
        print(f"New goal set:\n{json.dumps(response_json, indent=4)}")
        return next_goal

    async def evaluate_goal_completion(
        self,
        message_history: List[ChatCompletionMessageParam],
        goal: str,
        goal_screenshot_history: List[str],
    ) -> Tuple[bool, str]:
        """Evaluate if the current goal has been completed based on the action result."""

        eval_prompt = await evaluate_goal_completion_prompt(self.browser, goal)
        user_message = self.llm_client.create_user_message_with_images(
            eval_prompt, goal_screenshot_history, detail="high"
        )

        response = await self.llm_client.make_call(
            [
                *message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )

        if not response.content:
            raise ValueError(
                "No response content received from LLM in evaluate_goal_completion"
            )

        response_json = json.loads(response.content)
        completed = response_json["completed"]
        if completed:
            feedback = response_json["feedback"]
        else:
            feedback = (
                response_json["previous_action_evaluation"]
                + "\n\n"
                + response_json["feedback"]
            )

        print(f"Goal Evaluation:\n{json.dumps(response_json, indent=4)}")

        return completed, feedback

    async def evaluate_goal_validity(
        self,
        message_history: List[ChatCompletionMessageParam],
        goal: str,
        goal_screenshot_history: List[str],
    ) -> Tuple[bool, str]:
        eval_prompt = await evaluate_goal_validity_prompt(self.browser, goal)
        user_message = self.llm_client.create_user_message_with_images(
            eval_prompt, goal_screenshot_history, detail="high"
        )

        response = await self.llm_client.make_call(
            [
                *message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )

        if not response.content:
            raise ValueError(
                "No response content received from LLM in evaluate_goal_validity"
            )

        response_json = json.loads(response.content)
        should_update_goal = response_json["should_update_goal"]
        reasoning = response_json["reasoning"]
        print(f"Goal Validity Evaluation:\n{json.dumps(response_json, indent=4)}")

        return should_update_goal, reasoning


async def get_next_goal_prompt(browser: AgentBrowser) -> str:
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


CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


SCREENSHOTS:
The screenshots are ordered from top to bottom; the first screenshot is the top of the page and the last screenshot is the bottom of the page.


TASK: 
1. Describe the current state of the task. Outline what has been done so far and what remains to be done. If any mistakes were made and backtracking is needed, explain what went wrong and what needs to be done to correct it.
2. Determine what the immediate next goal should be. This typically should be a single action to take. The goal must be possible to complete on the current page. 

If you are stuck, assess the state of the page, brainstorm alternative strategies to proceed, and then determine the next goal. Don't repeatedly try the same thing if it's not working.

If the task is fully complete, suggest submitting for evaluation.


Output your response in JSON format.
{{
    "task_state": <description of the current state of the task>,
    "next_goal": <the next goal to accomplish>,
}}



Rules:
- Always use the extract action if you need to extract specific information from the page (recipe, top comment, title, etc.), even if you can see the information on the page.
- If you need to find a specific element on the page to interact with (e.g. a button, link, etc.), use the scroll_to_content action instead of the scroll action. Only use the scroll action if you need to view more of the page.
- When performing a search via a search bar, use a more general query if the current query is not working.
- For date inputs, type the desired date instead of using the date picker.
- If there is a dropdown menu, select an option before proceeding.
"""


async def evaluate_goal_completion_prompt(browser: AgentBrowser, goal: str) -> str:
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


CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK: 
1. Evaluate the outcome of the previous action. 
- If something unintended happened, explain what went wrong and what should be done to correct it. 
- If the previous action was the "extract" action, you don't need to verify the truthfulness of the extracted text.

2. Evaluate if the goal has been completed and provide feedback on the goal's completion. 
- If the goal is not completed, explain why and what needs to be done to complete the goal. If the goal is completed, briefly summarize what was done to complete the goal. 
- If you are stuck on completing the goal, brainstorm alternative strategies to complete the goal.

Goal: {goal}


Use the screenshots to evaluate if the goal has been completed. They capture the state of the page through time in chronological order.

Output your response in JSON format.
{{
    "previous_action_evaluation": <evaluation of the previous action>,
    "completed": <boolean indicating if the goal has been completed>,
    "feedback": <feedback>,
}}
"""


async def evaluate_goal_validity_prompt(browser: AgentBrowser, goal: str) -> str:
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


CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK: 
Determine if the current goal is still a good goal. Here are some examples of when the goal should be updated:
- If the goal is no longer relevant to the current page
- If the state change makes the current goal irrelevant, impossible, or suboptimal (e.g., an item goes out of stock, a required form field appears only after clicking submit)
- If a new error or notification appears that requires immediate attention (e.g., session timeout, captcha verification)
- If the website structure has changed significantly from what was expected (e.g., redirected to a different page)
- If a more efficient path to accomplish the overall task becomes available (e.g., a direct link appears)
- If prerequisites for the current goal need to be completed first (e.g., login required before proceeding)
- If the current goal was based on incorrect assumptions about the website's functionality
- If external factors have changed (e.g., price increases, availability changes)
- If the goal is too vague and needs to be made more specific based on the current page context


Current goal: {goal}

The screenshots capture the state of the page through time while the goal was being completed.


Output your response in JSON format.
{{
    "reasoning": <reasoning on why the goal should be updated or not>,
    "should_update_goal": <boolean indicating if the goal should be updated>,
}}
"""
