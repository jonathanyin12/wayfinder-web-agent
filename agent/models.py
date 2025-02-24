from dataclasses import dataclass
from typing import Any, List


@dataclass
class AgentAction:
    name: str
    description: str = None
    args: List[Any] = None

    def __post_init__(self):
        if self.args is None:
            self.args = []
