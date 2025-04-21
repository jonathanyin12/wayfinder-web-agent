import json
from typing import List, Tuple

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from agent.llm import LLMClient

SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Screenshots: This is a visual representation of the screen showing the process of performing a web task. It serves as visual proof of the actions taken in response to the instruction. The screenshots are ordered in chronological order.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshots and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- Use the screenshots as the source of truth for the state of the page. It's possible that the response contradicts the screenshot, in which case the screenshot prevails.
-- If you cannot verify information presented in the result response based on the screenshots, you should choose 'unknown'.

Provide a verdict on whether the task has been successfully accomplished, either as 'success', 'failed', or 'unknown'. If the task was not accomplished successfully, provide a feedback to the agent on what went wrong or what needs to be done to complete the task. If the task was completed successfully, explain why you think it was successful.

Output a JSON object with the following format:
{
    "verdict": <success | failed | unknown>
    "feedback": <feedback>
}"""


class TaskEvaluator:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.evaluator_model = "o4-mini"

    async def evaluate_task(
        self, task: str, final_response: str, screenshot_history: List[str]
    ) -> Tuple[bool, str]:
        """Evaluate the overall task completion based on the final response and screenshots."""

        user_message = self.llm_client.create_user_message_with_images(
            f"TASK: {task}\nResult Response: {final_response}",
            screenshot_history,
            detail="high",
        )
        response = await self.llm_client.make_call(
            [
                ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
                user_message,
            ],
            self.evaluator_model,
            json_format=True,
            timeout=240,
        )
        if not response.content:
            raise ValueError("No response from LLM in evaluate_task")

        response_json = json.loads(response.content)
        verdict = response_json["verdict"].lower()
        success = verdict != "failed"
        feedback = response_json["feedback"]

        print(f"Task Evaluation Verdict: {verdict}\n\nFeedback:\n{feedback}")

        return success, feedback
