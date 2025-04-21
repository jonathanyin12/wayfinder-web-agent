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


Your primary responsibility is to evaluate the task completion by:
1. Assessing whether the actions shown in screenshots and described in the response align with the web task instructions
2. Verifying that all conditions and parts of the instructions were met and completed successfully
3. Using screenshots as the definitive source of truth when explicit contradictions exist with the text response. The text response not being present in the screenshots is not a contradiction.

Note: The person performing the task is able to extract textual information from the page without scrolling to it first. As a result, it's possible some information they gathered in the result response cannot be verified through the screenshots. 

Rules:
- If there's no evidence in the screenshots to verify the information in the result response, you should choose 'unclear'.
- You should only choose 'failed' if you have explicit evidence that the task was not completed successfully.


Provide detailed feedback explaining:
- For successful tasks: Why the task was completed correctly
- For failed tasks: What went wrong and what should have been done differently
- For unclear verdicts: What information was missing to make a determination

Output a JSON object with the following format:
{
    "verdict": <success | failed | unclear>
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
