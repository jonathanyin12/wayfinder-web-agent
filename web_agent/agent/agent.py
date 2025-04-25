import time
from datetime import datetime
from typing import List, Tuple

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

from web_agent.agent.helpers.action_chooser import ActionChooser
from web_agent.agent.helpers.goal_manager import GoalManager
from web_agent.agent.helpers.task_evaluator import TaskEvaluator
from web_agent.agent.helpers.task_output_generator import TaskOutputGenerator
from web_agent.browser import AgentBrowser
from web_agent.llm import LLMClient
from web_agent.models import AgentAction

# Define a type alias for the return type of the run method
RunReturnType = Tuple[
    str, List[ChatCompletionMessageParam], List[str], List[str], int, float
]


def get_system_prompt(task: str) -> str:
    return f"""You are a web browsing assistant helping to complete the following task: "{task}"

Here are the possible actions you can take:
- click_element (element_id: int): click on an element on the page
- type_text (element_id: int, text: str): click on a text box and type text into it. This will automatically clear the text box before typing.
- scroll (direction: up | down, amount: float = 0.75): manually scroll the page in the given direction by the given amount
- navigate (direction: back | forward): go back to the previous page or go forward to the next page
- go_to_url (url: str): go to a specific url
- switch_tab (tab_index: int): switch to a different tab
- find (content_to_find: str): search the page for specific content and automatically scrolls to its location if found. Provide as much context/detail as possible about what you are looking for.
- extract (information_to_extract: str): Gets the entire text content of the page and extracts textual information based on a descriptive query.
- submit_for_evaluation: indicate that you believe the task is complete and ready for evaluation. An external reviewer will assess and provide feedback if any aspects of the task remain incomplete.


It is currently {datetime.now().strftime("%Y-%m-%d")}"""


class Agent:
    def __init__(
        self,
        task: str,
        llm_client: LLMClient,
        browser: AgentBrowser,
        output_dir: str,
        model: str = "gpt-4.1",
        max_iterations: int = 20,
    ):
        self.task = task
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = min(max_iterations, 20)
        self.model = model
        self.message_history: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system", content=get_system_prompt(task)
            )
        ]

        self.url_history: List[str] = []
        self.screenshot_history: List[str] = []
        self.include_captcha_check = False

        self.goal = "No goal yet"
        self.goal_screenshot_history: List[str] = []

        self.task_completed = False
        self.final_response = None

        self.include_prev_screenshots = True

        self.iteration = 0

        # Instantiate helpers
        self.goal_manager = GoalManager(llm_client, browser, model)
        self.action_chooser = ActionChooser(llm_client, browser, model)
        self.response_generator = TaskOutputGenerator(llm_client, model)
        self.task_evaluator = TaskEvaluator(llm_client)

    async def run(
        self,
    ) -> RunReturnType:
        """Run the task executor"""
        await self._initialize_run()

        while self.iteration < self.max_iterations and not self.task_completed:
            print(f"Iteration {self.iteration}")
            self.iteration += 1
            self.llm_client.print_token_usage(global_usage=True)
            # self.llm_client.print_message_history(
            #     cast(
            #         List[ChatCompletionMessageParam | Dict[str, Any]],
            #         self.message_history,
            #     )
            # )

            # Check for captcha first before planning the next action
            if self.include_captcha_check and await self.browser.check_for_captcha():
                await self._wait_for_human_input()
                continue

            # Get the next action using ActionChooser
            action = await self.action_chooser.choose_next_action(
                self.message_history, self.goal
            )

            # Add the action message to history
            action_message = ChatCompletionAssistantMessageParam(
                role="assistant",
                content=str(action),
            )
            self.message_history.append(action_message)

            if action.name == "submit_for_evaluation":
                final_response = await self.response_generator.prepare_final_response(
                    self.message_history, self.task
                )
                # Update the last message with the final response
                self.message_history[-1] = ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=str(action) + f"\n\n{final_response}",
                )

                # Use TaskEvaluator to evaluate completion
                success, feedback = await self.task_evaluator.evaluate_task(
                    self.task, final_response, self.screenshot_history
                )

                # Save the final response even if the task is not completed in case the evaluator is wrong
                self.final_response = final_response

                # Update state based on evaluation
                if success:
                    self.task_completed = success
                else:
                    # Add the feedback to history
                    evaluation_message = (
                        self.llm_client.create_user_message_with_images(
                            f"Task was deemed incomplete.\n\nFeedback:\n{feedback}",
                            [self.browser.current_page.screenshot]
                            if self.include_prev_screenshots
                            else [],
                            detail="high",
                        )
                    )
                    self.message_history.append(evaluation_message)
            else:
                # Execute the action
                success, action_result = await self._execute_action(action)

                # Update the goal and screenshot history since the action has been executed and page has been updated
                current_screenshot = self.browser.current_page.screenshot
                self.goal_screenshot_history.append(current_screenshot)
                self.screenshot_history.append(current_screenshot)
                if self.browser.current_page.page.url != self.url_history[-1]:
                    self.url_history.append(self.browser.current_page.page.url)

                # Evaluate goal completion
                if action_result:
                    # Add the action result to the message history
                    evaluation_message_history = [
                        *self.message_history,
                        ChatCompletionUserMessageParam(
                            role="user",
                            content=f"ACTION RESULT:\n{action_result}",
                        ),
                    ]
                else:
                    evaluation_message_history = self.message_history

                completed, feedback = await self.goal_manager.evaluate_goal_completion(
                    evaluation_message_history,
                    self.goal,
                    self.goal_screenshot_history,
                )

                await self._process_action_feedback_and_update_goal(
                    action_result, completed, feedback
                )

        self.end_time = time.time()
        self.llm_client.print_token_usage(global_usage=True)

        if not self.task_completed and self.final_response is None:
            self.final_response = (
                f"Failed to complete task within {self.max_iterations} iterations"
            )

        assert self.final_response is not None
        return (
            self.final_response,
            self.message_history,
            self.screenshot_history,
            self.url_history,
            self.iteration,
            self.end_time - self.start_time,
        )

    async def _initialize_run(self):
        print(f"Starting task: {self.task}")
        self.start_time = time.time()
        self.iteration = 0
        screenshot = self.browser.current_page.screenshot
        self.screenshot_history.append(screenshot)
        self.url_history.append(self.browser.current_page.page.url)
        # Use GoalManager to determine the next goal
        self.goal = await self.goal_manager.determine_next_goal(self.message_history)
        self.goal_screenshot_history = [screenshot]

        goal_message = self.llm_client.create_user_message_with_images(
            f"NEXT GOAL:\n{self.goal}",
            [screenshot] if self.include_prev_screenshots else [],
            detail="high",
        )
        self.message_history.append(goal_message)

    async def _execute_action(self, action: AgentAction):
        """Execute an action, get feedback if necessary, and update message history."""
        try:
            action_result = await self.browser.execute_action(action)
            if action_result:
                print(f"Action result:\n{action_result}")
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

    async def _process_action_feedback_and_update_goal(
        self, action_result: str, completed: bool, feedback: str
    ):
        """
        Process the action feedback and update the goal if necessary.

        This method handles the response after an action is executed. It formats the feedback
        message, determines if the current goal is completed, and updates the goal accordingly.
        If the goal is completed, it requests a new goal from the goal manager. The method also
        manages the screenshot history and creates appropriate user messages with images to
        maintain context for the LLM.
        """

        current_screenshot = self.browser.current_page.screenshot

        message_content = ""
        if action_result:
            # Add the action result to the message content
            message_content = f"ACTION RESULT:\n{action_result}\n\n"

        if completed:
            message_content = f"{message_content}PREVIOUS GOAL COMPLETED:\n{feedback}"
            # Determine the next goal
            self.goal = await self.goal_manager.determine_next_goal(
                [
                    *self.message_history,
                    self.llm_client.create_user_message_with_images(
                        message_content,
                        [current_screenshot],
                        detail="high",
                    ),
                ]
            )
            # Add the next goal to the message content
            message_content = f"{message_content}\n\nNEXT GOAL:\n{self.goal}"
            # Reset the goal screenshot history to just the current screenshot
            self.goal_screenshot_history = [current_screenshot]
        else:
            message_content = f"{message_content}FEEDBACK:\n{feedback}"
            (
                should_update_goal,
                reasoning,
            ) = await self.goal_manager.evaluate_goal_validity(
                [
                    *self.message_history,
                    ChatCompletionUserMessageParam(
                        role="user",
                        content=message_content,
                    ),
                ],
                self.goal,
                self.goal_screenshot_history,
            )
            if should_update_goal:
                self.goal = await self.goal_manager.determine_next_goal(
                    [
                        *self.message_history,
                        self.llm_client.create_user_message_with_images(
                            message_content,
                            [current_screenshot],
                            detail="high",
                        ),
                    ]
                )
                message_content = f"{message_content}\n\nUPDATED GOAL:\n{reasoning}\n\nNEXT GOAL:\n{self.goal}"
                self.goal_screenshot_history = [current_screenshot]
            else:
                self.goal_screenshot_history.append(current_screenshot)

        user_message = self.llm_client.create_user_message_with_images(
            message_content,
            [current_screenshot] if self.include_prev_screenshots else [],
            detail="high",
        )
        self.message_history.append(user_message)

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
