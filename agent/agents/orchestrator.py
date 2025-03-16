import json
from typing import List

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from agent.agents.task_executor.task_executor import TaskExecutor
from agent.browser.core.browser import AgentBrowser
from agent.llm.client import LLMClient


class Orchestrator:
    def __init__(
        self,
        objective: str,
        llm_client: LLMClient,
        browser: AgentBrowser,
        output_dir: str,
    ):
        self.objective = objective
        self.llm_client = llm_client
        self.browser = browser
        self.output_dir = output_dir

        self.max_iterations = 10
        self.model = "o1"
        self.message_history: List[ChatCompletionMessageParam] = []

        self.page_plan: List[str] = []
        self.plan_step = 0

    async def run(self):
        iteration = 0
        while iteration < self.max_iterations:
            next_task = await self._decide_next_task()

            task_executor = TaskExecutor(
                next_task, self.llm_client, self.browser, self.output_dir
            )
            success, result = await task_executor.run()
            if success:
                self.plan_step += 1

            print(result)

            iteration += 1

        return result

    async def _decide_next_task(self):
        """Decide the next task to execute"""
        if self.browser.current_page.is_new_page:
            print("NEW PAGE")
            system_prompt = f"""You are a helpful web browsing assistant that is tasked with completing the following objective: '{self.objective}'.

Here is an overview of the page you are currently on:
{self.browser.current_page.page_overview}
"""
            user_prompt = """Given the objective, what can be done on this page to get closer to achieving the objective?

- Be detailed and specific about what to do. Avoid ambiguity.
- Refer to the screenshot to understand the state of the page. Don't include steps for things that have already been done e.g. don't say sort by price if the price sorting has already been applied.


Output your plan in JSON format.
{{
    "plan": <list of steps to get closer to achieving the objective>
}}
"""
            user_message = self.llm_client.create_user_message_with_images(
                user_prompt, [self.browser.current_page.screenshot], "high"
            )
            response = await self.llm_client.make_call(
                [
                    ChatCompletionSystemMessageParam(
                        role="system", content=system_prompt
                    ),
                    user_message,
                ],
                self.model,
            )
            if not response.content:
                raise ValueError("No response from LLM")

            plan = json.loads(response.content)["plan"]
            print(json.dumps(plan, indent=4))
            self.page_plan = plan
            self.plan_step = 0

        return self.page_plan[self.plan_step]
