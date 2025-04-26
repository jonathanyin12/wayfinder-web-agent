from typing import TypedDict


class TaskData(TypedDict):
    web_name: str
    id: str
    ques: str  # Original objective field in the dataset
    objective: str  # Added field for clarity, usually the same as ques
    web: str


class EvaluationResult(TypedDict):
    verdict: str  # success | failed | unclear
    explanation: str
    eval_cost: float
    eval_model: str


class ReEvaluationResult(TypedDict):
    verdict: str  # success | failed
    explanation: str


class Metadata(TypedDict):
    objective: str
    final_response: str | dict
    id: str
    web_name: str
    ques: str
    web: str
    screenshot_path: str
    result_path: str
    duration: float
    message_history: str
    run_cost: float
    model: str
    iterations: int
    auto_eval: EvaluationResult | None  # Updated by auto_eval
    verdict_after_additional_verification: str | None  # Updated by eval_unclear
    additional_verification_reasoning: str | None  # Updated by eval_unclear
