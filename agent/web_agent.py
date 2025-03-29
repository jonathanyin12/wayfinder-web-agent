import json
import os
from datetime import datetime

from agent.agents.orchestrator.orchestrator import Orchestrator
from agent.browser.core.browser import AgentBrowser
from agent.llm import LLMClient


class WebAgent:
    def __init__(
        self,
        objective: str,
        initial_url: str = "about:blank",
        output_dir: str = "",
        headless: bool = False,
    ):
        self.objective = objective

        self.output_dir = (
            output_dir or f"runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self.browser = AgentBrowser(initial_url, self.output_dir, headless)
        self.llm_client = LLMClient()

    async def run(self):
        await self.browser.launch()
        orchestrator = Orchestrator(
            self.objective, self.llm_client, self.browser, self.output_dir
        )
        result, iterations, execution_time = await orchestrator.run()
        self.save_run(result, iterations, execution_time)

        await self.browser.terminate()

    def save_run(
        self,
        final_response,
        iterations,
        execution_time,
    ):
        token_usage = self.llm_client.get_token_usage()
        with open(os.path.join(self.output_dir, "metadata.json"), "w") as f:
            json.dump(
                {
                    "objective": self.objective,
                    "initial_url": self.browser.initial_url,
                    "iterations": iterations,
                    "final_response": final_response,
                    "execution_time": execution_time,
                    "token_usage": token_usage,
                },
                f,
                indent=4,
            )
