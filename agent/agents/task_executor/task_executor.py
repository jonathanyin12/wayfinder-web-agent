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

from agent.agents.task_executor.prompts import (
    get_action_choice_prompt,
    get_action_feedback_prompt,
    get_system_prompt,
    get_task_output_prompt,
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
        model: str = "gpt-4.1",
        max_iterations: int = 15,
    ):
        self.task = task
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = min(max_iterations, 15)
        self.model = model
        self.system_prompt = get_system_prompt(task)
        self.message_history: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=self.system_prompt)
        ]

        self.screenshot_history: List[str] = []
        self.include_captcha_check = False

    async def run(
        self,
    ) -> Tuple[str, List[ChatCompletionMessageParam], List[str], int, float]:
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
            success, action_result = await self._execute_action(action)

            if success:
                feedback = await self._give_action_feedback(action, action_result)
                self.message_history.append(
                    ChatCompletionUserMessageParam(role="user", content=feedback)
                )
                print(f"Action result: {feedback}")

            self.llm_client.print_token_usage()

            iteration += 1

        self.llm_client.print_token_usage()

        if iteration >= self.max_iterations:
            return (
                f"Failed to complete task within {self.max_iterations} iterations",
                self.message_history,
                self.screenshot_history,
                iteration,
                time.time() - start_time,
            )
        task_output = await self._prepare_task_output()
        return (
            task_output,
            self.message_history,
            self.screenshot_history,
            iteration,
            time.time() - start_time,
        )

    async def _choose_next_action(self) -> AgentAction:
        """Choose the next action to take

        Note: the benefit of not using o1 to choose the tool is that we get to output other metadata in the response, such as the action description and reasoning.
        """
        # Get action choice from primary model
        response_json = await self._get_action_choice()

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

        return action

    async def _get_action_choice(self) -> Dict[str, Any]:
        """Get action recommendation from the primary LLM"""
        # Get the action prompt and prepare the user message with image
        action_choice_prompt = await get_action_choice_prompt(self.browser)
        print(action_choice_prompt)
        images = [self.browser.current_page.bounding_box_screenshot]
        user_message = self.llm_client.create_user_message_with_images(
            action_choice_prompt, images, detail="high"
        )

        response = await self.llm_client.make_call(
            [
                *self.message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )

        if not response.content:
            raise ValueError("No response content received from LLM")

        response_json = json.loads(response.content)
        progress = response_json["progress"]
        reasoning = response_json["reasoning"]
        action_description = response_json["action_description"]
        formatted_response = f"Progress: {progress}\n\nReasoning: {reasoning}\n\nAction: {action_description}"
        print(f"Action choice:\n{formatted_response}")
        print(f"Action kwargs: {response_json['kwargs']}")

        self.message_history.append(
            ChatCompletionAssistantMessageParam(
                role="assistant",
                content=formatted_response,
            )
        )
        return response_json

    async def _convert_action_choice_to_tool_call(
        self, action_choice: Dict[str, Any]
    ) -> ChatCompletionMessageToolCall:
        """Create a tool call from an action choice"""
        action_name = action_choice["action_name"]
        action_description = action_choice["action_description"]
        kwargs = action_choice["kwargs"]

        progress = action_choice["progress"]
        reasoning = action_choice["reasoning"]

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content=f"""Perform the following action:\n{action_description}\nAction name: {action_name}\nAction kwargs: {kwargs}\n\nHere is the context for why you should perform this action:
            Progress: {progress}\n\nReasoning: {reasoning}""",
        )
        tool_call_message = await self.llm_client.make_call(
            [user_message],
            "gpt-4o-mini",
            tools=TOOLS,
        )
        if not tool_call_message.tool_calls:
            raise ValueError("No tool calls received from LLM")

        tool_call = tool_call_message.tool_calls[0]
        print(tool_call)
        return tool_call

    async def _execute_action(self, action: AgentAction):
        """Execute an action, get feedback if necessary, and update message history."""
        try:
            action_result = await self.browser.execute_action(action)
            return True, action_result
        except Exception as e:
            error_message = f"Error executing action '{action.description}': {e}"
            print(error_message)
            # Update page state after error
            await self.browser.update_page_state()
            # Add error message to history
            self.message_history.append(
                ChatCompletionUserMessageParam(role="user", content=error_message)
            )
            return False, error_message

    async def _give_action_feedback(
        self, action: AgentAction, action_result: str
    ) -> str:
        if action.name != "extract":
            action_feedback_prompt = get_action_feedback_prompt(action)
            user_message = self.llm_client.create_user_message_with_images(
                action_feedback_prompt,
                [
                    self.browser.current_page.previous_screenshot,
                    self.browser.current_page.screenshot,
                ],
                detail="high",
            )
            response = await self.llm_client.make_call(
                [user_message],
                "gpt-4.1",
                json_format=True,
            )

            if not response.content:
                print("Warning: No feedback content received from LLM")
                feedback = "Evaluation query failed."
            else:
                response_json = json.loads(response.content)
                feedback = response_json["evaluation"]

        if action_result:
            action_result = (
                f"Action output: {action_result}\n\nAction Evaluation:\n{feedback}"
            )
        else:
            action_result = f"Action Evaluation:\n{feedback}"

        return feedback

    async def _prepare_task_output(self) -> str:
        """Provide any information requested by the task."""

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content=get_task_output_prompt(self.task),
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
