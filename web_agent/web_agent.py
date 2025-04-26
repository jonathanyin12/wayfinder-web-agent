import json
import os
from datetime import datetime

from web_agent.agent.agent import Agent
from web_agent.browser.core.browser import AgentBrowser
from web_agent.llm import LLMClient


class WebAgent:
    def __init__(
        self,
        objective: str,
        initial_url: str = "about:blank",
        output_dir: str = "",
        max_iterations: int = 30,
        headless: bool = False,
        model: str = "gpt-4.1",
    ):
        self.objective = objective
        self.model = model
        self.output_dir = (
            output_dir or f"runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self.llm_client = LLMClient()

        self.browser = AgentBrowser(
            initial_url, self.output_dir, headless, self.llm_client
        )
        self.max_iterations = max_iterations

    async def run(self):
        await self.browser.launch()
        agent = Agent(
            task=self.objective,
            llm_client=self.llm_client,
            browser=self.browser,
            output_dir=self.output_dir,
            model=self.model,
            max_iterations=self.max_iterations,
        )
        (
            result,
            message_history,
            screenshot_history,
            url_history,
            iterations,
            execution_time,
        ) = await agent.run()
        print(result)
        self.save_run(result, message_history, url_history, iterations, execution_time)

        await self.browser.terminate()

    def save_run(
        self,
        final_response,
        message_history,
        url_history,
        iterations,
        execution_time,
    ):
        token_usage = self.llm_client.get_token_usage()
        total_cost = self.llm_client.get_total_cost()
        prettified_message_history = self.llm_client.format_message_history(
            message_history
        )
        with open(os.path.join(self.output_dir, "metadata.json"), "w") as f:
            json.dump(
                {
                    "objective": self.objective,
                    "initial_url": self.browser.initial_url,
                    "iterations": iterations,
                    "final_response": final_response,
                    "url_history": url_history,
                    "execution_time": execution_time,
                    "token_usage": token_usage,
                    "run_cost": total_cost,
                    "primary_model": self.model,
                    "message_history": prettified_message_history,
                },
                f,
                indent=4,
            )
