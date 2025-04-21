import json
from typing import List

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from agent.llm import LLMClient


def get_task_output_prompt(task: str) -> str:
    return f"""TASKS:   
1. Reason about whether the task requires any information to be returned.

2. Provide a final response to the task.
- If the task was not completed, briefly explain why not.
- If the task requires information to be returned, reference the message history to find the requested information and return it. DO NOT MAKE UP ANY INFORMATION. If information requested for the task is not present in the message history, simply state what information is missing.

As a reminder, the task is: {task}
            

Output your response in JSON format.
{{
    "reasoning": <reasoning about whether the task requires any information to be returned>,
    "requires_information": <True if the task requires information to be returned, False otherwise>,
    "response": <final response to the task>,
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

        print(final_response)
        return final_response
