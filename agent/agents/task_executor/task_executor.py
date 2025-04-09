import json
import time
from typing import Any, Dict, List, Tuple

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
        task: str,
        llm_client: LLMClient,
        browser: AgentBrowser,
        output_dir: str,
        max_iterations: int = 15,
    ):
        self.task = task
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = min(max_iterations, 15)
        self.model = "gpt-4o"
        self.message_history: List[ChatCompletionMessageParam] = []
        self.screenshot_history: List[str] = []

        self.include_captcha_check = False

    async def run(self) -> Tuple[str, List[str], int, float]:
        print(f"Starting task: {self.task}")
        start_time = time.time()
        iteration = 0
        while iteration < self.max_iterations:
            self.screenshot_history.append(self.browser.current_page.screenshot)
            # Check for captcha first before planning the next action
            if self.include_captcha_check and await self.browser.check_for_captcha():
                await self._wait_for_human_input()
                continue

            # Get the next action
            action = await self._choose_next_action()

            if action.name == "end_task":
                break

            # Execute the action
            await self._execute_action(action)

            self.llm_client.print_token_usage()

            iteration += 1

        self.llm_client.print_token_usage()

        if iteration >= self.max_iterations:
            return (
                f"Failed to complete task within {self.max_iterations} iterations",
                self.screenshot_history,
                iteration,
                time.time() - start_time,
            )
        task_output = await self._prepare_task_output()
        return (
            task_output,
            self.screenshot_history,
            iteration,
            time.time() - start_time,
        )

    def _get_system_prompt(self) -> str:
        return f"""You are a web browsing assistant helping to complete the following task: "{self.task}"

Here are the possible actions you can take:
- click_element (element_id: int): click on an element on the page
- type_text (element_id: int, text: str): type text into a text box on the page and optionally submit the text
- scroll (direction: up | down, amount: float = 0.75): manually scroll the page in the given direction by the given amount
- scroll_to_content (content_to_find: str): automatically scroll to specific content on the page. Use this if you need to find something that is not currently visible e.g. a button that is not visible. Provide as much context/detail as possible about what you are looking for.
- extract (information_to_extract: str): Performs OCR and extracts textual information from the current page based on a descriptive query of what you are looking for e.g. "recipe and ingredients", "first paragraph", "top comment" etc.
- navigate (direction: back | forward): go back to the previous page or go forward to the next page
- go_to_url (url: str): go to a specific url
- switch_tab (tab_index: int): switch to a different tab
- end_task: declare that you have completed the task


Guidelines:
- Always use the extract action if you need to extract specific information from the page (recipe, top comment, title, etc.), even if you can see the information on the page.
- If you need to find a specific element on the page to interact with (e.g. a button, link, etc.), use the scroll_to_content action instead of the scroll action. Only use the scroll action if you need to view more of the page.
- When searching via a search bar, use a more general keyword query if a more specific query is not working.

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
        page_overview = page.page_overview
        interactable_elements = get_formatted_interactable_elements(
            pixels_above, pixels_below, page.elements
        )
        tabs = await get_formatted_tabs(self.browser)
        return f"""TASK:
1. Give a progress summary
- Briefly describe what has been done so far and what still needs to be done.
- Is the objective complete?
- Has all the information requested in the objective been extracted and is present in the message history?


2. Reason about what action to take next.
- Consider the elements you can currently see and interact with on the page.
- Don't repeatedly try actions that aren't working. Find an alternative strategy.
- If the task is complete, respond with the action "end_task".


Finally, respond with a JSON object with the following fields:
{{
    "progress": <summary of what you have done so far and what you still need to do>,
    "reasoning": <reasoning for choosing this action>,
    "action_description": <one sentence description of the action you will perform>,
    "action_name": <name of the action to take>,
    "kwargs": <kwargs for the action>,
}}


OPEN BROWSER TABS:
{tabs}

SCREENSHOT: 
the current visible portion of the page with bounding boxes drawn around interactable elements. The element IDs are the numbers in top-left of boxes.

PAGE POSITION:
{page_position}

PAGE OVERVIEW:
{page_overview}

CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}
"""

    async def _execute_action(self, action: AgentAction):
        """Execute an action, get feedback if necessary, and update message history."""
        action_result_str = None
        try:
            assert action.tool_call is not None
            # Execute the action
            action_result_str = await self.browser.execute_action(action)

            # Provide feedback on all actions except extract
            if action.name != "extract":
                message = f"""Based on the two screenshots, evaluate whether the following action was completed successfully.

Intended action: {action.description}

Action performed: {action.name} {f"(on {action.element.get('description', '')})" if action.element else ""}

The first screenshot is the state of the page before the action, and the second screenshot is the state of the page after the action. Consider what UX changes are expected for the action.
- If no visible change occured, consider why e.g. perhaps the action was selecting on option that was already selected.
- Make sure the intended action was actually completed. 

Output your verdict as a JSON object with the following fields:
{{
    "reasoning": <reasoning about whether the action was completed successfully>,
    "evaluation": <statement about the action's outcome, making sure to restate the action, with a brief explanation of why the action was completed or not>,
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
                    json_format=True,
                )

                if not response.content:
                    print("Warning: No feedback content received from LLM")
                    feedback = "Evaluation query failed."
                else:
                    response_json = json.loads(response.content)
                    feedback = response_json["evaluation"]

                if action_result_str:
                    action_result_str = (
                        f"Action output: {action_result_str}\n\nEvaluation: {feedback}"
                    )
                else:
                    action_result_str = feedback

            # Append the final result/feedback to history
            self.message_history.append(
                ChatCompletionUserMessageParam(role="user", content=action_result_str)
            )
            print(f"Action result: {action_result_str}")

        except Exception as e:
            print(f"Error executing action '{action.description}': {e}")
            # Update page state after error
            await self.browser.update_page_state()
            # Add error message to history
            error_message = f"Error executing action '{action.description}': {e}"
            self.message_history.append(
                ChatCompletionUserMessageParam(role="user", content=error_message)
            )
            print(f"Action failed: {error_message}")

    async def _prepare_task_output(self) -> str:
        """Provide any information requested by the task."""

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content=f"""TASK 1:            
Provide a 1-2 sentence final response to the task. If the task was not completed, briefly explain why not.

As a reminder, the task is: {self.task}

TASK 2:
Determine if the task requires any information to be returned. If so, reference the message history to find the requested information and return it. DO NOT MAKE UP ANY INFORMATION. If information requested for the task is not present in the message history, simply state what information is missing.
            

Output your response in JSON format.
{{
    "response": <final response to the task>,
    "reasoning": <reasoning about whether the task requires any information to be returned>,
    "information": <Return the content requested by the task in natural language. If no information is requested, return an empty string>,
}}""",
        )

        response = await self.llm_client.make_call(
            [
                *self.message_history,
                user_message,
            ],
            "gpt-4o",
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response from LLM")
        response_json = json.loads(response.content)

        final_response = response_json["response"]
        information = response_json["information"]
        if information:
            formatted_response = f"{final_response}\n\n{information}"
        else:
            formatted_response = final_response
        return formatted_response

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
