from typing import TypedDict


class TaskData(TypedDict):
    web_name: str
    id: str
    ques: str
    web: str


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
