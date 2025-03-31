import json
import time
from typing import List

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

from agent.agents.task_executor.task_executor import TaskExecutor
from agent.agents.utils.prompt_formatting import (
    get_formatted_page_position,
    get_formatted_tabs,
)
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
        self.message_history: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=f"""You are a helpful web browsing assistant that is tasked with completing the following objective: '{self.objective}'.""",
            )
        ]

        self.plan = "No plan yet"

    async def run(self):
        start_time = time.time()
        iteration = 0
        while iteration < self.max_iterations:
            next_task = await self._decide_next_task()
            if next_task == "objective complete":
                break

            self.message_history.append(
                ChatCompletionUserMessageParam(
                    role="user",
                    content=next_task,
                )
            )
            task_executor = TaskExecutor(
                self.objective,
                next_task,
                self.llm_client,
                self.browser,
                self.output_dir,
            )
            success, result = await task_executor.run()
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=result,
                )
            )
            print(result)
        return result, iteration, time.time() - start_time

    async def _decide_next_task(self):
        """Make a plan for the next task"""
        tabs = await get_formatted_tabs(self.browser)
        page_overview = self.browser.current_page.page_overview
        (
            pixels_above,
            pixels_below,
        ) = await self.browser.current_page.get_pixels_above_below()
        page_position = get_formatted_page_position(
            pixels_above,
            pixels_below,
        )
        user_prompt = f"""TASK:
1. Make a rough plan to complete the objective from the current state.
- Consider the things that have already been done and what still needs to be done.
- Update the previous plan if it is no longer valid (e.g. need to backtrack). Make sure to remove any steps that have already been completed.
- It's okay to be unsure or less detailed about later steps.
- You can evaluate whether previous steps were successful or not, but don't include that in the plan unless a mistake was made and it needs to be corrected.

Previous plan:
{self.plan}


2. Then, output what should be done next according to the plan (typically the first step). This information will be passed to the task executor.
- Study the screenshot and page overview to understand the current state of the page.
- This should only focus on the current page and not future pages.
- Avoid ambiguity. Don't say something vague like "explore/review the results". The scope should also be clear. 
- Focus more on outcomes rather than prescribing specific actions.
- Provide all the context needed to complete the next step within the instructions. The task executor won't be able to see past messages, so make sure to include all the information it needs to complete the next step.


If the objective is complete and there are no more steps to take, just say "objective complete" for the next step.


Output your plan in JSON format.
{{
    "progress": <brief summary of what has been done so far>
    "plan": <description of the overall plan, in markdown format>
    "next_step": <what should be done next>
}}


CURRENT STATE:

Browser tabs:
{tabs}
 
Page overview:
{page_overview}

Page position: {page_position}

Screenshots: shows the current visible portion of the page
"""

        user_message = self.llm_client.create_user_message_with_images(
            user_prompt, [self.browser.current_page.screenshot], "high"
        )
        # self.llm_client.print_message_history(
        #     [
        #         *self.message_history,
        #         user_message,
        #     ]
        # )
        response = await self.llm_client.make_call(
            [
                *self.message_history,
                user_message,
            ],
            self.model,
        )
        if not response.content:
            raise ValueError("No response from LLM")

        response_json = json.loads(response.content)
        print(json.dumps(response_json, indent=4))
        plan = response_json["plan"]
        next_step = response_json["next_step"]
        self.plan = plan

        return next_step
