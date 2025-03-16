import os
from datetime import datetime

from agent.agents.task_executor.task_executor import TaskExecutor
from agent.browser.core.browser import AgentBrowser
from agent.llm import LLMClient


class WebAgent:
    # Configuration and Initialization
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

        # Components
        self.llm_client = LLMClient()

        self.max_iterations = 10

    async def run(self):
        await self.browser.launch()

        task_executor = TaskExecutor(
            self.objective, self.llm_client, self.browser, self.output_dir
        )
        result = await task_executor.run()
        print(result)

        await self.browser.terminate()
