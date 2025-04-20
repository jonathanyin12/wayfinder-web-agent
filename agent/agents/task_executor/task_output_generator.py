import json
from typing import List

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from agent.llm import LLMClient


def get_task_output_prompt(task: str) -> str:
    return f"""TASK 1:            
Provide a 1-2 sentence final response to the task. If the task was not completed, briefly explain why not.

As a reminder, the task is: {task}

TASK 2:
Determine if the task requires any information to be returned. If so, reference the message history to find the requested information and return it. DO NOT MAKE UP ANY INFORMATION. If information requested for the task is not present in the message history, simply state what information is missing.
            

Output your response in JSON format.
{{
    "response": <final response to the task>,
    "reasoning": <reasoning about whether the task requires any information to be returned>,
    "information": <Return the content requested by the task in natural language. If no information is requested, return an empty string>,
}}"""


class TaskOutputGenerator:
    def __init__(self, llm_client: LLMClient, model: str):
        self.llm_client = llm_client
        self.model = model

    async def prepare_final_response(
        self, message_history: List[ChatCompletionMessageParam], task: str
    ) -> str:
        """Prepare the final response for the task based on the history."""

        user_message = ChatCompletionUserMessageParam(
            role="user",
            content=get_task_output_prompt(task),
        )

        response = await self.llm_client.make_call(
            [
                *message_history,
                user_message,
            ],
            self.model,
            json_format=True,
        )
        if not response.content:
            raise ValueError("No response from LLM in prepare_final_response")
        response_json = json.loads(response.content)

        final_response = response_json["response"]
        information = response_json["information"]
        if information:
            formatted_response = f"{final_response}\n\n{information}"
        else:
            formatted_response = final_response

        print(formatted_response)
        return formatted_response
