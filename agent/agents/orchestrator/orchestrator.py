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
                content=f"""You are a helpful manager that is tasked with overseeing the completion of the following objective: '{self.objective}'.

You are working with a web browsing assistant, who will perform the actual actions and an evaluator, who will evaluate the results of the performance of the web browsing assistant.

You are responsible for planning and delegating tasks to the web browsing assistant and adjusting the plan if necessary based on the evaluator's feedback.
""",
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
                ChatCompletionAssistantMessageParam(
                    role="assistant",
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
            result, screenshot_history = await task_executor.run()
            evaluation = await self._evaluate_task_execution(
                next_task,
                result,
                screenshot_history,
            )

            formatted_result = f"Web browsing assistant's response: {result}\n\nEvaluator's feedback: {evaluation}"
            self.message_history.append(
                ChatCompletionUserMessageParam(
                    role="user",
                    content=formatted_result,
                )
            )

            print(formatted_result)

        final_response = await self._prepare_final_response()
        return final_response, iteration, time.time() - start_time

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

Previous plan:
{self.plan}


2. Then, output what should be done next according to the plan (typically the first step). This information will be passed to the web browsing assistant.
- Study the screenshot and page overview to understand the current state of the page.
- Make sure the task is actually possible and focuses on the current page and not future pages.
- Avoid ambiguity. Don't say something vague like "explore/review the results". The scope should also be clear. 
- Provide all the context needed to complete the next step within the instructions. The web browsing assistant won't be able to see past messages, so make sure to include all the information it needs to complete the next step.


If the objective is complete, just say "objective complete" for the next step.


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

Screenshot: shows the current visible portion of the page
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

    async def _evaluate_task_execution(
        self,
        task: str,
        result: str,
        screenshot_history: List[str],
    ):
        SYSTEM_PROMPT = """As an evaluator, your job is to evaluate a web browsing assistant's performance on a given task. You will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.
-- If you are not sure whether you should believe the content in the response, you should choose unknown.


Summarize what the web browsing assistant did according to the screenshots and determine whether the task was successfully accomplished. If the task was not completed successfully, explain why not.
"""

        USER_PROMPT = f"""TASK: {task}
        Result Response: {result}"""
        user_message = self.llm_client.create_user_message_with_images(
            USER_PROMPT, screenshot_history, "high"
        )

        response = await self.llm_client.make_call(
            [
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=SYSTEM_PROMPT,
                ),
                user_message,
            ],
            "gpt-4o",
            json_format=False,
        )
        if not response.content:
            raise ValueError("No response from LLM")

        return response.content

    async def _prepare_final_response(self) -> str:
        """Prepare the final response to relay to the user"""

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content="""Provide a final response about the completed web browsing task. Include:
1. A summary of what happened
2. (If applicable) Detailed information gathered during the task (e.g., product specifications, prices, availability, recipes, reviews, etc.)

Make sure to include all relevant information that fulfills the original objective.""",
        )

        response = await self.llm_client.make_call(
            [
                *self.message_history,
                user_message,
            ],
            "gpt-4o",
            json_format=False,
        )
        if not response.content:
            raise ValueError("No response from LLM")
        print(f"Final response: {response.content}")
        return response.content
