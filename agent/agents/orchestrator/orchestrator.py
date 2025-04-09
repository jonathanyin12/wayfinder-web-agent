import json
import time
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

        self.max_iterations = 15
        self.model = "o1"
        self.message_history: List[ChatCompletionMessageParam] = []

        self.plan = "No plan yet"

    async def run(self) -> Tuple[str, int, float]:
        start_time = time.time()
        iteration = 0

        information_needed = await self._identify_information_needed()
        self.information_needed = information_needed
        system_prompt = f"""You are a helpful manager that is tasked with overseeing the completion of the following objective: '{self.objective}'."""
        if information_needed:
            system_prompt += f"\n\nHere is the information likely needed to complete the objective: {information_needed}\n\nBefore deeming the objective complete, make sure to have extracted all the information needed since the user will only be able to see the text in your final response."

        self.message_history.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=system_prompt,
            )
        )

        while iteration < self.max_iterations:
            progress, plan, next_task = await self._decide_next_task()
            self.plan = plan
            if next_task == "objective complete":
                break
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=next_task,
                )
            )
            task_executor = TaskExecutor(
                next_task,
                self.llm_client,
                self.browser,
                self.output_dir,
                max_iterations=self.max_iterations - iteration,
            )
            (
                task_output,
                screenshot_history,
                iterations,
                execution_time,
            ) = await task_executor.run()
            evaluation = await self._evaluate_task_execution(
                next_task,
                task_output,
                screenshot_history,
            )
            if task_output:
                formatted_result = f"Task output:\n{task_output}\n\n---------------------\n\nEvaluation:\n{evaluation}"
            else:
                formatted_result = f"{evaluation}"
            print(formatted_result)
            self.message_history.append(
                ChatCompletionUserMessageParam(
                    role="user",
                    content=formatted_result,
                )
            )

            iteration += iterations

        if next_task.lower().strip() == "objective complete":
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=f"Progress: {progress}\n\nPlan: {plan}\n\nThe objective has been completed.",
                )
            )
        else:
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content="The objective was not completed with the given number of iterations.",
                )
            )

        final_response = await self._prepare_final_response()
        print(f"Final response:\n{final_response}")
        self.llm_client.print_token_usage()
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
1. Give a progress summary
- Briefly describe what has been done so far and what still needs to be done.
- Has all the information requested in the objective been extracted and is present in the message history?

Information needed:
{self.information_needed if self.information_needed else "None"}


2. Make a basic plan to complete the objective from the current state.
- Keep the plan simple and straightforward. Don't overcomplicate things. Only do what is necessary to complete the objective.
- Update the previous plan if it is no longer valid (e.g. need to backtrack). Make sure to remove any steps that have already been completed.
- It's okay to be unsure or less detailed about later steps.

Previous plan:
{self.plan}


3. Provide instructions for what should be done next on the current page.
- Study the screenshot and page overview to understand the current state of the page.
- Make sure the task is actually possible and focuses on the current page and not future pages.
- Avoid ambiguity. Don't say something vague like "explore/review the results". The scope should also be clear.
- Provide all the context needed to complete the next step within the instructions. The web browsing assistant won't be able to see past messages, so make sure to include all the information it needs to complete the next step.

If you have completed the objective and extracted all the information requested, say "objective complete" for the next step.


Output your plan in JSON format.
{{
    "progress": <brief summary of what has been done so far>
    "plan": <description of the  plan, in markdown format>
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
        progress = response_json["progress"]
        plan = response_json["plan"]
        next_step = response_json["next_step"]
        print(f"Progress: {progress}\n\nPlan: {plan}\n\nNext step: {next_step}")

        return progress, plan, next_step

    async def _evaluate_task_execution(
        self,
        task: str,
        result: str,
        screenshot_history: List[str],
    ):
        PROMPT = f"""As an evaluator, your job is to evaluate a web browsing assistant's performance on a given task.

TASK: {task}

TASK OUTPUT: {result}

Screenshots are provided to help you evaluate the task output. This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

Guidelines:
-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.

Summarize what the web browsing assistant did according to the screenshots and determine whether the task was successfully accomplished. If the task was not completed successfully, explain why not.

Output your evaluation in JSON format.
{{
    "summary": <summary of what the web browsing assistant did>,
    "reasoning": <reasoning about whether the task was completed successfully>,
    "evaluation": <statement about the task's outcome, making sure to restate the task, with a brief explanation of why the task was completed or not>,
}}"""

        user_message = self.llm_client.create_user_message_with_images(
            PROMPT, screenshot_history, "high"
        )

        response = await self.llm_client.make_call(
            [user_message],
            "gpt-4o",
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response from LLM")

        response_json = json.loads(response.content)
        return response_json["evaluation"]

    async def _prepare_final_response(self) -> str:
        """Prepare the final response to relay to the user"""

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content="""TASK 1:            
Provide a 1-2 sentence final response to the objective. If the objective was not completed, briefly explain why not.


TASK 2:
If the objective requires information to be returned, make sure to include all the information gathered. Otherwise, return an empty string for the information field.
- Reference the message history to find the requested information. DO NOT MAKE UP ANY INFORMATION. 
- If information requested for the task is not present in the message history, simply state what information is missing. 


Output your response in JSON format with the following fields:
{{
    "response": <final response to the objective>,
    "information": <detailed information gathered that fulfills the objective. If no information is needed, return an empty string>,
}}
""",
        )

        response = await self.llm_client.make_call(
            [
                *self.message_history,
                user_message,
            ],
            "gpt-4o",
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response from LLM")

        response_json = json.loads(response.content)

        final_response = response_json["response"]
        information = response_json["information"]
        if information:
            formatted_response = f"{final_response}\n\n{information}"
        else:
            formatted_response = final_response
        return formatted_response

    async def _identify_information_needed(self) -> str:
        """Determine the requested information from the objective"""

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content=f"""Determine if the objective requires any information to be returned. If so, clearly outline what information is needed to complete the objective.
            
Objective: '{self.objective}'

Output your response in JSON format with the following fields:
{{
    "reasoning": <reasoning about whether the objective requires any information to be returned>,
    "information_needed": <boolean indicating whether information is needed to complete the objective>,
    "information": <detailed natural language description of the information needed to complete the objective. If no information is needed, return an empty string>,
}}""",
        )

        response = await self.llm_client.make_call(
            [user_message],
            "gpt-4o",
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response from LLM")

        response_json = json.loads(response.content)
        if response_json["information_needed"]:
            print(
                f"Information needed to complete the objective:\n{response_json['information']}"
            )
        else:
            print("No information needed to complete the objective")
        return response_json["information"]
