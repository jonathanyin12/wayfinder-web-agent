import json
import time
from typing import Any, Dict, List, Tuple

from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from agent.agents.task_executor.prompts import (
    evaluate_goal_completion_prompt,
    get_action_choice_prompt,
    get_evaluator_system_prompt,
    get_next_goal_prompt,
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

        self.goal = "No goal yet"
        self.feedback = ""
        self.goal_screenshot_history: List[str] = []

        self.task_completed = False

    async def run(
        self,
    ) -> Tuple[str, List[ChatCompletionMessageParam], List[str], int, float]:
        print(f"Starting task: {self.task}")
        start_time = time.time()
        iteration = 0

        await self._determine_next_goal()
        goal_message = self.llm_client.create_user_message_with_images(
            f"NEXT GOAL:\n{self.goal}",
            [self.browser.current_page.screenshot],
            detail="high",
        )
        self.message_history.append(goal_message)
        self.goal_screenshot_history.append(self.browser.current_page.screenshot)

        while iteration < self.max_iterations and not self.task_completed:
            self.screenshot_history.append(self.browser.current_page.screenshot)
            # Check for captcha first before planning the next action
            if self.include_captcha_check and await self.browser.check_for_captcha():
                await self._wait_for_human_input()
                continue

            # Get the next action
            action = await self._choose_next_action()

            if action.name == "submit_for_evaluation":
                final_response = await self._prepare_task_output()
                success, reasoning = await self._task_evaluation(final_response)
                if success:
                    self.task_completed = True
                    return (
                        final_response,
                        self.message_history,
                        self.screenshot_history,
                        iteration,
                        time.time() - start_time,
                    )
                else:
                    self.message_history.append(
                        ChatCompletionUserMessageParam(
                            role="user",
                            content=f"Task was deemed incomplete.\n\nReasoning:\n{reasoning}",
                        )
                    )
                    continue

            # Execute the action
            success, action_result = await self._execute_action(action)

            self.goal_screenshot_history.append(self.browser.current_page.screenshot)
            completed, feedback = await self._evaluate_goal_completion(action_result)

            if completed:
                # Create a temporary message to pass in the action result and feedback
                temporary_message = f"GOAL COMPLETED:\n{feedback}"
                if action_result:
                    temporary_message = (
                        f"ACTION RESULT:\n{action_result}\n\n{temporary_message}"
                    )
                user_message = self.llm_client.create_user_message_with_images(
                    temporary_message,
                    [self.browser.current_page.screenshot],
                    detail="high",
                )
                self.message_history.append(user_message)

                await self._determine_next_goal()
                self.message_history.pop()  # pop the temporary message

                message = f"GOAL COMPLETED:\n{feedback}\n\nNEXT GOAL:\n{self.goal}"
                if action_result:
                    message = f"ACTION RESULT:\n{action_result}\n\n{message}"

                user_message = self.llm_client.create_user_message_with_images(
                    message,
                    [self.browser.current_page.screenshot],
                    detail="high",
                )
                self.message_history.append(user_message)
                self.feedback = ""
                self.goal_screenshot_history.append(
                    self.browser.current_page.screenshot
                )
            else:
                message = f"FEEDBACK:\n{feedback}"
                if action_result:
                    message = f"ACTION RESULT:\n{action_result}\n\n{message}"

                user_message = self.llm_client.create_user_message_with_images(
                    message,
                    [self.browser.current_page.screenshot],
                    detail="high",
                )
                self.message_history.append(user_message)

                self.feedback = feedback

            self.llm_client.print_token_usage()
            self.llm_client.print_message_history(self.message_history)
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

    async def _determine_next_goal(self):
        next_goal_prompt = await get_next_goal_prompt(self.browser)

        user_message = self.llm_client.create_user_message_with_images(
            next_goal_prompt, [self.browser.current_page.screenshot], detail="high"
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
        self.goal = response_json["next_goal"]
        print(f"New goal set:\n{json.dumps(response_json, indent=4)}")
        self.goal_screenshot_history = []

    async def _evaluate_goal_completion(self, action_result: str) -> Tuple[bool, str]:
        """Evaluate if the goal has been completed"""

        next_goal_prompt = await evaluate_goal_completion_prompt(
            self.browser, self.goal, action_result
        )
        user_message = self.llm_client.create_user_message_with_images(
            next_goal_prompt, self.goal_screenshot_history, detail="high"
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

    async def _choose_next_action(self) -> AgentAction:
        """Choose the next action to take

        Note: the benefit of not using o1 to choose the tool is that we get to output other metadata in the response, such as the action description and reasoning.
        """
        # Get action choice from primary model
        action_choice_prompt = await get_action_choice_prompt(
            self.browser, self.goal, self.feedback
        )
        images = [self.browser.current_page.bounding_box_screenshot]
        user_message = self.llm_client.create_user_message_with_images(
            action_choice_prompt, images, detail="high"
        )
        tool_call_message = await self.llm_client.make_call(
            [
                *self.message_history,
                user_message,
            ],
            self.model,
            tools=TOOLS,
        )
        if not tool_call_message.tool_calls:
            raise ValueError("No tool calls received from LLM")

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

        self.message_history.append(
            ChatCompletionAssistantMessageParam(
                role="assistant",
                content=str(action),
            )
        )
        print(tool_call)

        return action

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

    async def _task_evaluation(self, final_response: str) -> Tuple[bool, str]:
        """Evaluate the task"""
        evaluator_system_prompt = await get_evaluator_system_prompt()

        user_message = self.llm_client.create_user_message_with_images(
            f"TASK: {self.task}\nResult Response: {final_response}",
            self.screenshot_history,
            detail="high",
        )
        response = await self.llm_client.make_call(
            [
                ChatCompletionSystemMessageParam(
                    role="system", content=evaluator_system_prompt
                ),
                user_message,
            ],
            "o4-mini",
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response from LLM")
        response_json = json.loads(response.content)
        verdict = response_json["verdict"]
        success = verdict == "success"
        feedback = response_json["feedback"]
        return success, feedback

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
