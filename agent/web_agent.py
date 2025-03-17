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
        await orchestrator.run()
        await self.browser.terminate()
