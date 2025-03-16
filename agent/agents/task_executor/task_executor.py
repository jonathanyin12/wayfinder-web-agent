import asyncio
import json
from typing import Any, Dict, List, Optional

from agent.agents.utils.prompt_formatting import (
    get_formatted_interactable_elements,
    get_formatted_page_position,
    get_formatted_tabs,
)
from agent.browser.core.tools import TOOLS
from agent.models import AgentAction

from ...browser import AgentBrowser
from ...llm import LLMClient


class TaskExecutor:
    def __init__(
        self, task: str, llm_client: LLMClient, browser: AgentBrowser, output_dir: str
    ):
        self.task = task
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = 5
        self.model = "o1"
        self.message_history: List[Dict[str, Any]] = []

    async def run(self):
        print(f"Starting task: {self.task}")
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # Run captcha check and planning concurrently
            captcha_task = asyncio.create_task(self.browser.check_for_captcha())
            action_task = asyncio.create_task(self._choose_next_action())

            captcha_detected = await captcha_task
            if captcha_detected:
                # Cancel action task if still running
                if not action_task.done():
                    action_task.cancel()
                    try:
                        await action_task  # Allow cancellation to process
                    except asyncio.CancelledError:
                        pass  # Ignore the cancellation error
                await self._wait_for_human_input()
                continue

            action = await action_task

            await self._execute_action(action)

            # self.llm_client.print_message_history(self.message_history)
            self.llm_client.print_token_usage()

            if action.name == "end":
                break

        print(f"Completed task in {iteration} iterations.")

    def _get_system_prompt(self) -> str:
        return f"""You are a helpful web browsing assistant. Your job is to complete the following task: {self.task}

Here are the possible actions you can take:
- click_element: click a specific element on the page
- type_text: type text into a text box on the page and optionally submit the text
- scroll: scroll up or down on the page. Refer to the full page overview to determine whether scrolling could help you find what you are looking for.
- navigate: go back to the previous page or go forward to the next page
- go_to_url: go to a specific url
- switch_tab: switch to a different tab
- end: declare that you have completed the task


PAGE OVERVIEW:
{self.browser.current_page.page_overview}
"""

    async def _choose_next_action(self) -> AgentAction:
        """Choose the next action to take

        Note: having o1 directly choose the right function call is very expensive for some reason. It is cheaper to have o1 select the action and then have another model make the actual function call. An added benefit of this is that we get some visibility into the action selection process.
        """

        action_prompt = await self._get_action_prompt()

        images = [self.browser.current_page.bounding_box_screenshot]
        user_message = self.llm_client.create_user_message_with_images(
            action_prompt, images, detail="high"
        )
        response = await self.llm_client.make_call(
            [
                {"role": "system", "content": self._get_system_prompt()},
                *self.message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response content received from LLM")

        response_json = json.loads(response.content)
        print(f"Action choice:\n{json.dumps(response_json, indent=2)}")

        tool_call_message = await self.llm_client.make_call(
            [
                {
                    "role": "user",
                    "content": f"Perform the following action:\n{json.dumps(response_json, indent=2)}",
                }
            ],
            "gpt-4o-mini",
            tools=TOOLS,
        )
        if not tool_call_message.tool_calls:
            raise ValueError("No tool calls received from LLM")

        tool_call = tool_call_message.tool_calls[0]
        function_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        action = AgentAction(
            name=function_name,
            element=self.browser.current_page.elements.get(
                args.get("element_id", -1), {}
            ),
            description=response_json["action_description"],
            reasoning=response_json["reasoning"],
            args=args,
            id=tool_call.id,
        )
        # Append tool call message to history
        self.message_history.append(tool_call_message.model_dump())

        return action

    async def _get_action_prompt(
        self,
    ) -> str:
        """Returns the prompt template for planning the next action"""

        page = self.browser.current_page
        pixels_above, pixels_below = await page.get_pixels_above_below()
        page_position = get_formatted_page_position(pixels_above, pixels_below)
        interactable_elements = get_formatted_interactable_elements(
            pixels_above, pixels_below, page.elements
        )
        tabs = await get_formatted_tabs(self.browser)
        return f"""OPEN BROWSER TABS:
{tabs}

SCREENSHOT: 
the current visible portion of the page with bounding boxes drawn around interactable elements. The element IDs are the numbers in top-left of boxes.

PAGE POSITION:
{page_position}

CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK:
1. Reason about what action to take next based on the current page, the task you have been given, and the actions you have already taken.
- Consider the elements you can currently see and interact with on the page.
- Are you looking for a specific element on the page that is not currently visible? According to the page overview, is it located in a section of the page that you have not yet scrolled to?
- Don't repeat actions that have already been performed unless the action failed.

2. Choose a single action to perform next. Provide all the relevant information needed to perform the action.
- If the action involves clicking on an element, provide the element ID.
- If the action involves typing text into a text box, provide the element ID and the text to type.
- If the action involves scrolling, provide the direction to scroll.

Finally, respond with a JSON object with the following fields:
{{
    "action_description": <one sentence description of the action you will perform>,
    "action_name": <name of the action to take>,
    "args": <list of arguments for the action, if any>,
    "reasoning": <reasoning for choosing this action>
}}"""

    async def _execute_action(self, action: AgentAction) -> Optional[str]:
        try:
            result = await self.browser.execute_action(action)

            action_content = f"Performed the following action: '{action.description}'"
            if result:
                action_content += f"\nResult: {result}"

            # Append tool message to history
            self.message_history.append(
                {
                    "role": "tool",
                    "tool_call_id": action.id,
                    "content": action_content,
                }
            )
            return result
        except Exception as e:
            print(f"Error executing action: {e}")
            print("Trying again next iteration...")
            # Remove last two messages from history on failure
            if len(self.message_history) >= 2:
                self.message_history = self.message_history[:-2]
            await self.browser.update_page_state()
            return None

    # Human Control Methods
    async def _wait_for_human_input(self) -> None:
        """Wait for human to press Enter to yield control back to agent"""
        self.required_human_input = True
        while True:
            try:
                user_input = input(
                    "Press 'Enter' when you want to yield control back to the agent."
                )
                if user_input == "":  # Empty string means Enter was pressed
                    print("Yielding control back to the agent.")
                    await self.browser.update_page_state()
                    break
                print("Please press 'Enter' key only.")
            except KeyboardInterrupt:
                print("Interrupted by user. Terminating...")
                break
