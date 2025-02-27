import asyncio
import contextlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .browser import AgentBrowser
from .browser.core.action_executor import TOOLS
from .llm import LLMClient, PromptManager
from .models import AgentAction

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Agent:
    # Configuration and Initialization
    def __init__(
        self,
        identity: str = "",
        objective: str = "",
        action_model: str = "gpt-4o",
        planning_model: str = "o1",
        default_url: str = "about:blank",
    ):
        # Agent Configuration
        self.action_model = action_model
        self.planning_model = planning_model
        self.default_url = default_url

        # Agent State
        self.identity = identity
        self.objective = objective  # The objective of the agent (e.g. "buy a macbook")
        self.message_history: List[Dict[str, Any]] = [
            {"role": "system", "content": PromptManager(objective).get_system_prompt()}
        ]
        self.action_history: List[AgentAction] = []

        # Components
        self.llm_client = LLMClient()
        self.prompt_manager = PromptManager(objective)
        self.browser = AgentBrowser()

        self.iteration = 0

    @contextlib.asynccontextmanager
    async def _timed_operation(self, description: str):
        """Context manager for timing operations"""
        start_time = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            logger.info(f"{description} took {elapsed:.2f} seconds")

    # Main Control Flow Methods
    async def launch(self, url: Optional[str] = None, headless: bool = False) -> None:
        """Launch the agent with the specified URL or default URL."""
        target_url = url or self.default_url
        await self.browser.launch(target_url, headless)
        await self.execute_agent_loop()
        await self.browser.terminate()

    async def execute_agent_loop(self) -> None:
        """Main agent loop: observe, plan, and execute actions."""
        logger.info(f"BEGINNING TASK: {self.objective}")

        while True:
            self.iteration += 1

            # Run captcha check and planning concurrently
            captcha_task = asyncio.create_task(self._check_for_captcha())
            planning_task = asyncio.create_task(self._plan_next_action_with_timing())

            # Wait for captcha check to complete first
            captcha_detected = await captcha_task
            if captcha_detected:
                # Cancel planning task if still running
                if not planning_task.done():
                    planning_task.cancel()
                    try:
                        await planning_task  # Allow cancellation to process
                    except asyncio.CancelledError:
                        pass  # Ignore the cancellation error

                logger.info("Captcha detected. Yielding control to human.")
                await self._wait_for_human_input()
                continue

            # If no captcha, wait for planning to complete
            planning_response = await planning_task

            # Format the response for history
            formatted_response = self._format_planning_response(planning_response)
            self._append_to_history("user", formatted_response)
            logger.info(json.dumps(planning_response, indent=4))

            # Action selection phase
            next_step = planning_response["next_step"]
            async with self._timed_operation("Choosing action"):
                action = await self._choose_next_action(next_step)
                logger.info(f"Selected action: {action}")

            # Execution phase
            async with self._timed_operation("Execution"):
                outcome = await self._execute_action(action)
                if outcome:
                    logger.info(f"Action outcome: {outcome}")
                else:
                    logger.warning("Action execution failed. Replanning...")

            # Print token usage
            self.llm_client.print_token_usage()

            # Check for completion
            if action.name == "end":
                logger.info(
                    f"Completed task in {self.iteration} iterations. Exiting..."
                )
                break

    # LLM Methods
    def _append_to_history(self, role: str, content: Any) -> None:
        """Helper method to append messages to history"""
        self.message_history.append(
            {
                "role": role,
                "content": content,
            }
        )

    # Helper methods
    async def _check_for_captcha(self) -> bool:
        """Check for captcha with timing."""
        async with self._timed_operation("Captcha check"):
            return await self.browser.check_for_captcha()

    async def _plan_next_action_with_timing(self) -> Dict[str, Any]:
        """Plan next action with timing."""
        async with self._timed_operation("Planning"):
            return await self._plan_next_action()

    # Main Methods
    async def _plan_next_action(self) -> Dict[str, Any]:
        """Evaluate the current page and plan the next action"""
        # Prepare planning prompt
        planning_prompt = await self.prompt_manager.get_planning_prompt(
            self.browser.get_site_name(),
            await self.browser.get_formatted_page_position(),
            self.browser.page.url,
            await self.browser.get_formatted_interactable_elements(),
            last_action=self.action_history[-1] if self.action_history else None,
        )

        # Prepare images
        images = []
        if self.browser.previous_page_screenshot_base64:
            images.append(self.browser.previous_page_screenshot_base64)
        images.append(self.browser.current_page_screenshot_base64)

        # Create content with text and images
        user_message = self.llm_client.create_user_message_with_images(
            planning_prompt, images, detail="low"
        )

        # Prepare and send message
        messages = [*self.message_history, user_message]

        try:
            response = await self.llm_client.make_call(messages, self.planning_model)
            response_json = json.loads(response)
            return response_json
        except Exception as e:
            logger.error(f"Error in planning: {str(e)}")
            # Return a minimal valid response to avoid crashing
            return {"page_summary": "Error in planning", "next_step": "Retry"}

    def _format_planning_response(self, response_json: Dict[str, Any]) -> str:
        """Format the planning response for history"""
        parts = [f"Page summary: {response_json['page_summary']}"]

        if "previous_action_evaluation" in response_json:
            parts.append(
                f"Previous action outcome: {response_json['previous_action_evaluation']}"
            )

        if "progress" in response_json:
            parts.append(f"Progress: {response_json['progress']}")

        parts.append(f"Next step: {response_json['next_step']}")

        return "\n\n".join(parts)

    async def _choose_next_action(self, next_step: str) -> AgentAction:
        """Choose the next action to take"""
        # Prepare action prompt
        action_prompt = await self.prompt_manager.get_action_prompt(
            self.browser.get_site_name(),
            await self.browser.get_formatted_page_position(),
            self.browser.page.url,
            await self.browser.get_formatted_interactable_elements(),
            next_step,
        )

        # Prepare images for action selection
        images = [
            self.browser.current_page_screenshot_base64,
            self.browser.current_annotated_page_screenshot_base64,
        ]

        # Create content with text and images
        user_message = self.llm_client.create_user_message_with_images(
            action_prompt, images
        )

        # Prepare and send message
        messages = [self.message_history[0], user_message]

        tool_call_message = await self.llm_client.make_call(
            messages, self.action_model, tools=TOOLS
        )
        # Append tool call message to history
        self.message_history.append(tool_call_message)

        tool_call = tool_call_message.tool_calls[0]
        function_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        action = AgentAction(
            name=function_name,
            html_element=self.browser.label_simplified_htmls.get(
                args.get("element_id", -1)
            ),
            args=args,
            id=tool_call.id,
        )
        self.action_history.append(action)
        return action

    async def _execute_action(self, action: AgentAction) -> Optional[str]:
        """Execute the next action in the plan. Returns outcome."""
        try:
            result = await self.browser.execute_action(action)
            # Append tool message to history
            self.message_history.append(
                {
                    "role": "tool",
                    "tool_call_id": action.id,
                    "content": str(result),
                }
            )
            return result
        except Exception as e:
            logger.error(f"Error executing action: {e}")
            logger.info("Trying again next iteration...")
            # Remove last two messages from history on failure
            if len(self.message_history) >= 2:
                self.message_history = self.message_history[:-2]
            await self.browser.update_browser_state()
            return None

    # Human Control Methods
    async def _wait_for_human_input(self) -> None:
        """Wait for human to press Enter to yield control back to agent"""
        while True:
            try:
                user_input = input(
                    "Press 'Enter' when you want to yield control back to the agent."
                )
                if user_input == "":  # Empty string means Enter was pressed
                    logger.info("Yielding control back to the agent.")
                    await self.browser.update_browser_state()
                    break
                logger.info("Please press 'Enter' key only.")
            except KeyboardInterrupt:
                logger.info("Interrupted by user. Terminating...")
                await self.terminate()
                break
