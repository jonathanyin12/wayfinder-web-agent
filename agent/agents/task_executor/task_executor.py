import json
from typing import Any, Dict, List

from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_message_tool_call_param import (
    ChatCompletionMessageToolCallParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import (
    Function as ToolCallParamFunction,
)
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
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
        self, task: str, llm_client: LLMClient, browser: AgentBrowser, output_dir: str
    ):
        self.task = task
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = 10
        self.model = "o1"
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

            if action.name == "finish_task":
                break

            # Execute the action
            success = await self._execute_action(action)
            if not success:
                print("Action execution failed. Trying again next iteration...")

            self.llm_client.print_token_usage()

            iteration += 1

        self.llm_client.print_token_usage()

        if iteration >= self.max_iterations:
            return False, "Failed to complete task"

        return True, action.args.get("final_response")

    def _get_system_prompt(self) -> str:
        return f"""You are a helpful web browsing assistant. Your job is to complete the following task: "{self.task}"

Here are the possible actions you can take:
- click_element (element_id: int): click on an element on the page
- type_text (element_id: int, text: str): type text into a text box on the page and optionally submit the text
- find (content_to_find: str): find content on the page. If you are looking for something on the current page that is not visible, use this action. Provide as much context/detail as possible about what you are looking for.
- navigate (direction: back | forward): go back to the previous page or go forward to the next page
- go_to_url (url: str): go to a specific url
- switch_tab (tab_index: int): switch to a different tab
- finish_task (reason: str, final_response: str): declare that you have completed the task and no further actions are needed


PAGE OVERVIEW:
{self.browser.current_page.page_overview}
"""

    async def _choose_next_action(self) -> AgentAction:
        """Choose the next action to take

        Note: the benefit of not using o1 to choose the tool is that we get to output other metadata in the response, such as the action description and reasoning.
        """
        # Get the action prompt and prepare the user message with image
        action_prompt = await self._get_action_prompt()
        images = [self.browser.current_page.bounding_box_screenshot]
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

SCREENSHOT: 
the current visible portion of the page with bounding boxes drawn around interactable elements. The element IDs are the numbers in top-left of boxes.

PAGE POSITION:
{page_position}

CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK:
1. Reason about what action to take next based on the current page, the task you have been given, and the actions you have already taken.
- Consider the elements you can currently see and interact with on the page as well as the previous images.
- Are you looking for a specific element on the page that is not currently visible? According to the page overview, is it located in a section of the page that you have not yet scrolled to?
- Don't repeat actions that have already been performed unless the action failed.

2. Choose a single action to perform next. Provide all the relevant information needed to perform the action.
- If you are clicking on an element, provide the element ID.
- If you are typing text into a text box, provide the element ID and the text to type.
- If you are scrolling, provide the direction to scroll.
- If you are finishing the task, provide the final response to the task and a reason for why you believe you have completed the task.

Finally, respond with a JSON object with the following fields:
{{
    "progress": <summary of what you have done so far and what you still need to do>,
    "reasoning": <reasoning for choosing this action>,
    "action_description": <one sentence description of the action you will perform>,
    "action_name": <name of the action to take>,
    "kwargs": <kwargs for the action, if any>,
}}"""

    async def _execute_action(self, action: AgentAction) -> bool:
        """Execute an action and return whether it was successful"""
        try:
            assert action.tool_call is not None
            result = await self.browser.execute_action(action)

            # Add tool call to history
            tool_call = action.tool_call
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ChatCompletionMessageToolCallParam(
                            function=ToolCallParamFunction(
                                name=tool_call.function.name,
                                arguments=tool_call.function.arguments,
                            ),
                            id=tool_call.id,
                            type=tool_call.type,
                        )
                    ],
                )
            )
            # Append tool output to history
            tool_output = f"Performed the following action: '{action.description}'"
            if result:
                tool_output += f"\nResult: {result}"

            self.message_history.append(
                ChatCompletionToolMessageParam(
                    role="tool",
                    tool_call_id=action.tool_call.id,
                    content=tool_output,
                )
            )
            return True
        except Exception as e:
            print(f"Error executing action: {e}")
            # Update page state after error
            await self.browser.update_page_state()
            return False

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
