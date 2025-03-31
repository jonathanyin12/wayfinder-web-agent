import json
from typing import Any, Dict, List

from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

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
        self,
        objective: str,
        task: str,
        llm_client: LLMClient,
        browser: AgentBrowser,
        output_dir: str,
    ):
        self.objective = objective
        self.task = task
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = 10
        self.model = "gpt-4o"
        self.message_history: List[ChatCompletionMessageParam] = []

        self.include_captcha_check = False

    async def run(self):
        print(f"Starting task: {self.task}")
        iteration = 0
        while iteration < self.max_iterations:
            # Check for captcha first before planning the next action
            if self.include_captcha_check and await self.browser.check_for_captcha():
                await self._wait_for_human_input()
                continue

            # Get the next action
            action = await self._choose_next_action()

            if action.name == "end_task":
                break

            # Execute the action
            action_result = await self._execute_action(action)
            await self._provide_action_feedback(action, action_result)

            self.llm_client.print_token_usage()

            iteration += 1

        self.llm_client.print_token_usage()

        if iteration >= self.max_iterations:
            return False, "Failed to complete task"

        return True, action.args.get("final_response")

    def _get_system_prompt(self) -> str:
        return f"""You are a web browsing assistant helping to complete one part of the following objective: "{self.objective}"

Your specific task is the following: "{self.task}"

Here are the possible actions you can take:
- click_element (element_id: int): click on an element on the page
- type_text (element_id: int, text: str): type text into a text box on the page and optionally submit the text
- scroll (content_to_find: str): scroll to find content on the page. Provide as much context/detail as possible about what you are looking for.
- navigate (direction: back | forward): go back to the previous page or go forward to the next page
- go_to_url (url: str): go to a specific url
- switch_tab (tab_index: int): switch to a different tab
- end_task (final_response: str): declare that you have completed the task and provide a final response


Here is an overview of the current page:
{self.browser.current_page.page_overview}
"""

    async def _choose_next_action(self) -> AgentAction:
        """Choose the next action to take

        Note: the benefit of not using o1 to choose the tool is that we get to output other metadata in the response, such as the action description and reasoning.
        """
        # Get the action prompt and prepare the user message with image
        action_prompt = await self._get_action_prompt()
        images = [
            self.browser.current_page.screenshot,
            self.browser.current_page.bounding_box_screenshot,
        ]
        user_message = self.llm_client.create_user_message_with_images(
            action_prompt, images, detail="high"
        )

        # Get action choice from primary model
        response_json = await self._get_action_choice(user_message)
        print(f"Action choice:\n{json.dumps(response_json, indent=2)}")

        # Convert to a tool call
        tool_call = await self._convert_action_choice_to_tool_call(response_json)
        args = json.loads(tool_call.function.arguments)

        action = AgentAction(
            name=tool_call.function.name,
            element=self.browser.current_page.elements.get(
                args.get("element_id", -1), {}
            ),
            description=response_json["action_description"],
            reasoning=response_json["reasoning"],
            args=args,
            tool_call=tool_call,
        )

        # user_message = self.llm_client.create_user_message_with_images(
        #     "", images, detail="high"
        # )
        # self.message_history.append(user_message)

        return action

    async def _get_action_choice(
        self, user_message: ChatCompletionMessageParam
    ) -> Dict[str, Any]:
        """Get action recommendation from the primary LLM"""
        system_message = ChatCompletionSystemMessageParam(
            role="system", content=self._get_system_prompt()
        )
        response = await self.llm_client.make_call(
            [
                system_message,
                *self.message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )

        if not response.content:
            raise ValueError("No response content received from LLM")

        response_json = json.loads(response.content)
        self.message_history.append(
            ChatCompletionAssistantMessageParam(
                role="assistant",
                content=response.content,
            )
        )
        return response_json

    async def _convert_action_choice_to_tool_call(
        self, action_choice: Dict[str, Any]
    ) -> ChatCompletionMessageToolCall:
        """Create a tool call from an action choice"""
        user_message = ChatCompletionUserMessageParam(
            role="user",
            content=f"Perform the following action:\n{json.dumps(action_choice, indent=2)}",
        )
        tool_call_message = await self.llm_client.make_call(
            [user_message],
            "gpt-4o-mini",
            tools=TOOLS,
        )
        if not tool_call_message.tool_calls:
            raise ValueError("No tool calls received from LLM")

        tool_call = tool_call_message.tool_calls[0]
        return tool_call

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

SCREENSHOTS: 
First screenshot: the current visible portion of the page.
Second screenshot: the current visible portion of the page with bounding boxes drawn around interactable elements. The element IDs are the numbers in top-left of boxes.

PAGE POSITION:
{page_position}

CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK:
1. Reason about whether you have completed the task.
- Consider the actions you have already taken and the progress you have made.
- Don't interpret the task too narrowly.

2. Reason about what action to take next.
- Consider the elements you can currently see and interact with on the page.
- Use the scroll action if you need to find something that is not currently visible.
- Don't repeatedly try actions that aren't working. Find an alternative strategy.
- If the task is complete, respond with the action "end_task".


Finally, respond with a JSON object with the following fields:
{{
    "progress": <summary of what you have done so far and what you still need to do>,
    "reasoning": <reasoning for choosing this action>,
    "action_description": <one sentence description of the action you will perform>,
    "action_name": <name of the action to take>,
    "kwargs": <kwargs for the action>,
}}"""

    async def _execute_action(self, action: AgentAction) -> str | None:
        """Execute an action and return the result"""
        try:
            assert action.tool_call is not None
            result = await self.browser.execute_action(action)

            return result
        except Exception as e:
            print(f"Error executing action: {e}")
            # Update page state after error
            await self.browser.update_page_state()

    async def _provide_action_feedback(
        self, action: AgentAction, action_result: str | None = None
    ):
        if not action_result:
            """Provide feedback on the most recent action"""
            message = f"""Based on the two screenshots, evaluate whether the following action was completed successfully. 

Action: {action.description}

The first screenshot is the state of the page before the action, and the second screenshot is the state of the page after the action. Consider what UX changes are expected for the action.
- If no visible change occured, consider why e.g. perhaps the action was selecting on option that was already selected.

Output your verdict as a JSON object with the following fields:
{{  
    "reasoning": <reasoning about whether the action was completed successfully>,
    "evaluation": <statement about the action's outcome, making sure to restate the action>,
}}"""

            user_message = self.llm_client.create_user_message_with_images(
                message,
                [
                    self.browser.current_page.previous_screenshot,
                    self.browser.current_page.screenshot,
                ],
                detail="high",
            )

            response = await self.llm_client.make_call(
                [user_message],
                "gpt-4o",
            )

            if not response.content:
                raise ValueError("No response content received from LLM")

            response_json = json.loads(response.content)

            action_result = response_json["evaluation"]

        self.message_history.append(
            ChatCompletionUserMessageParam(
                role="user",
                content=action_result or "",  # Provide fallback for None
            )
        )
        print(f"Action result: {action_result}")

    # Human Control Methods
    async def _wait_for_human_input(self) -> None:
        """Wait for human to press Enter to yield control back to agent"""
        print("Captcha detected. Human intervention required.")
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
