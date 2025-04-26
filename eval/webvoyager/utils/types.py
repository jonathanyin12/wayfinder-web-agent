from typing import TypedDict


class TaskData(TypedDict):
    web_name: str
    id: str
    ques: str  # Original objective field in the dataset
    web: str


class Evaluation(TypedDict):
    verdict: str  # success | failed | unclear
    explanation: str
    cost: float
    model: str


class EvaluationResult(TypedDict):
    final_verdict: str  # success | failed | unclear
    evaluation: Evaluation
    re_evaluation: Evaluation | None


class Metadata(TypedDict):
    objective: str
    initial_url: str
    iterations: int
    final_response: str
    url_history: list[str]
    execution_time: float
    token_usage: dict
    run_cost: float
    primary_model: str
    message_history: str
    evaluation_result: EvaluationResult | None
