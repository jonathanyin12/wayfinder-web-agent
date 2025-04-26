MODEL_PRICING = {
    "gpt-4o-mini": {
        "prompt_tokens": 0.15 / 1000000,
        "completion_tokens": 0.6 / 1000000,
    },
    "gpt-4o": {
        "prompt_tokens": 2.5 / 1000000,
        "completion_tokens": 10 / 1000000,
    },
    "o1": {
        "prompt_tokens": 15 / 1000000,
        "completion_tokens": 60 / 1000000,
    },
    "gpt-4.1": {
        "prompt_tokens": 2 / 1000000,
        "completion_tokens": 8 / 1000000,
    },
    "o4-mini": {
        "prompt_tokens": 1.1 / 1000000,
        "completion_tokens": 4.4 / 1000000,
    },
    "o3": {
        "prompt_tokens": 10 / 1000000,
        "completion_tokens": 40 / 1000000,
    },
}


INITIAL_EVALUATION_SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Screenshots: This is a visual representation of the screen showing the process of performing a web task. It serves as visual proof of the actions taken in response to the instruction. The screenshots are ordered in chronological order.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.


Your primary responsibility is to evaluate the task completion by:
1. Assessing whether the actions shown in screenshots and described in the response align with the web task instructions
2. Verifying that all conditions and parts of the instructions were met and completed successfully
3. Using screenshots as the definitive source of truth when explicit contradictions exist with the text response. The text response not being present in the screenshots is not a contradiction.

Note: The person performing the task is able to extract textual information from the page without scrolling to it first. As a result, it's possible some information they gathered in the result response cannot be verified through the screenshots.

Rules:
- IF THERE'S NO EVIDENCE IN THE SCREENSHOTS TO VERIFY THE INFORMATION IN THE RESULT RESPONSE, YOU SHOULD CHOOSE 'UNCLEAR'.
- IF YOU HAVE EXPLICIT EVIDENCE THAT THE TASK WAS NOT COMPLETED SUCCESSFULLY, YOU SHOULD CHOOSE 'FAILED'
- IF THE PERSON PERFORMING THE TASK CHALLENGES THE FEASIBILITY OF THE TASK, YOU SHOULD CHOOSE 'FAILED'
- IF THE PERSON PERFORMING THE TASK SAID THEY DID NOT COMPLETE THE TASK, YOU SHOULD CHOOSE 'FAILED'


Provide detailed feedback explaining:
- For successful tasks: Why the task was completed correctly
- For failed tasks: What went wrong and what should have been done differently
- For unclear verdicts: What information was missing to make a determination


Output a JSON object with the following format:
{
    "verdict": <success | failed | unclear>
    "explanation": <explanation>
}
"""

INITIAL_EVALUATION_USER_PROMPT_TEMPLATE = """TASK: <task>
Result Response: <answer>
The last <num> screenshots are attached. """


REEVALUATION_PROMPT_TEMPLATE = """You are a helpful assistant whose job is to verify whether a task was completed successfully. You are working alongside another evaluator, who has already provided an evaluation, in which they felt like the success of the task was unclear. You will be given the task, the user's response, along with some other information, which you can assume to be true, and the evaluator's evaluation. Your job is to verify whether the task was completed successfully.

Task: {objective}
User's Final response:{final_response}

Evaluator's Evaluation:
{eval_reasoning}


Additional Information (You can trust this information):
{formatted_extract_outputs}
--------------------------------------------------


If the main objection of the the evaluator's reasoning is that the screenshots do not provide evidence for information in the user's final response, but the additional information provided does, you should return success.

If the user challenges the feasibility of the task, you should return failure.


Output a JSON object with the following fields:
{{
    "verdict": "success" | "failure",
    "explanation": str,
}}
"""
