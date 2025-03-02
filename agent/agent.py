import asyncio
import contextlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .browser import TOOLS, AgentBrowser
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
        initial_url: str = "about:blank",
        output_dir: str = "",
    ):
        # Agent Configuration
        self.action_model = action_model
        self.planning_model = planning_model
        self.initial_url = initial_url

        # Components
        self.llm_client = LLMClient()
        self.prompt_manager = PromptManager(objective, self.llm_client)
        self.output_dir = (
            output_dir or f"runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self.browser = AgentBrowser(self.output_dir)

        # Agent State
        self.identity = identity
        self.objective = objective  # The objective of the agent (e.g. "buy a macbook")
        self.message_history: List[Dict[str, Any]] = [
            {"role": "system", "content": self.prompt_manager.get_system_prompt()}
        ]
        self.action_history: List[AgentAction] = []

        self.required_human_input = False
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
    async def execute(self, headless: bool = False) -> None:
        """Launch the agent with the specified URL or default URL."""
        await self.browser.launch(self.initial_url, headless)
        await self._execute_agent_loop()
        await self.browser.terminate()

    async def _execute_agent_loop(self) -> None:
        """Main agent loop: observe, plan, and execute actions."""
        logger.info(f"BEGINNING TASK: {self.objective}")
        self.start_time = time.time()
        while self.iteration < 50:
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

            self._add_plan_to_message_history(planning_response)

            # Action selection phase
            async with self._timed_operation("Choosing action"):
                action = await self._choose_next_action(planning_response)
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
                break

        if self.iteration >= 50:
            logger.info("Max iterations reached. Exiting...")
        else:
            logger.info(f"Completed task in {self.iteration} iterations.")
            logger.info(f"Final result: {action.args['final_response']}")
            self._save_execution_history(action.args["final_response"])

    # Helper methods
    async def _check_for_captcha(self) -> bool:
        """Check for captcha with timing."""
        async with self._timed_operation("Captcha check"):
            return await self.browser.check_for_captcha()

    async def _plan_next_action_with_timing(self) -> Dict[str, Any]:
        """Plan next action with timing."""
        async with self._timed_operation("Planning"):
            return await self._plan_next_action()

    def _add_plan_to_message_history(self, response_json: Dict[str, Any]) -> None:
        """Format the planning response for history"""
        parts = [f"Page summary: {response_json['page_summary']}"]

        if "previous_action_evaluation" in response_json:
            parts.append(
                f"Previous action outcome: {response_json['previous_action_evaluation']}"
            )

        if "progress" in response_json:
            parts.append(f"Progress: {response_json['progress']}")

        parts.append(f"Next step: {response_json['next_step']}")

        formatted_response = "\n\n".join(parts)
        print(formatted_response)
        # Add the formatted planning response to message history
        self.message_history.append({"role": "user", "content": formatted_response})

    def _save_execution_history(self, final_response: str):
        """Save execution data to a file."""
        # Save raw message history
        message_history_path = os.path.join(self.output_dir, "raw_message_history.json")
        with open(message_history_path, "w", encoding="utf-8") as f:
            json.dump(self.message_history, f, indent=2)
        logger.info(f"Saved message history to {message_history_path}")

        # Save formatted message history for better readability
        formatted_history_path = os.path.join(
            self.output_dir, "formatted_message_history.txt"
        )
        formatted_history = self.llm_client.format_message_history(self.message_history)
        with open(formatted_history_path, "w", encoding="utf-8") as f:
            f.write(formatted_history)
        logger.info(f"Saved formatted message history to {formatted_history_path}")

        # Save meta data associated with the run
        meta_data_path = os.path.join(self.output_dir, "meta_data.json")
        meta_data = {
            "objective": self.objective,
            "action_model": self.action_model,
            "planning_model": self.planning_model,
            "initial_url": self.initial_url,
            "iterations": self.iteration,
            "final_response": final_response,
            "execution_time": time.time() - self.start_time,
            "token_usage": self.llm_client.token_usage,
            "required_human_input": self.required_human_input,
        }
        with open(meta_data_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)
        logger.info(f"Saved meta data to {meta_data_path}")

    # Main Methods
    async def _plan_next_action(self) -> Dict[str, Any]:
        """Evaluate the current page and plan the next action"""
        # Prepare planning prompt
        user_message = await self.prompt_manager.build_planning_message(
            self.browser,
            last_action=self.action_history[-1] if self.action_history else None,
        )

        # Prepare and send message
        messages = [*self.message_history, user_message]

        try:
            response = await self.llm_client.make_call(messages, self.planning_model)
            if not response.content:
                raise ValueError("Empty response content")
            response_json = json.loads(response.content)
            return response_json
        except Exception as e:
            logger.error(f"Error in planning: {str(e)}")
            # Return a minimal valid response to avoid crashing
            return {"page_summary": "Error in planning", "next_step": "Retry"}

    async def _choose_next_action(
        self, planning_response: Dict[str, Any]
    ) -> AgentAction:
        """Choose the next action to take"""
        # Prepare action prompt
        user_message = await self.prompt_manager.build_action_message(
            self.browser, planning_response
        )

        # Prepare and send message
        messages = [self.message_history[0], user_message]
        tool_call_message = await self.llm_client.make_call(
            messages, self.action_model, tools=TOOLS
        )
        # Append tool call message to history
        self.message_history.append(tool_call_message.model_dump())

        if not tool_call_message.tool_calls:
            raise ValueError("No tool calls received from LLM")

        tool_call = tool_call_message.tool_calls[0]
        function_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        action = AgentAction(
            name=function_name,
            html_element=self.browser.pages[
                self.browser.current_page_index
            ].label_simplified_htmls.get(args.get("element_id", -1), ""),
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
                    logger.info("Yielding control back to the agent.")
                    await self.browser.update_page_state()
                    break
                logger.info("Please press 'Enter' key only.")
            except KeyboardInterrupt:
                logger.info("Interrupted by user. Terminating...")
                break
