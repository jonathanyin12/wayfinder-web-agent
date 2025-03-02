from dataclasses import dataclass
from typing import Any, List


@dataclass
class AgentAction:
    name: str
    html_element: str = ""
    args: List[Any] = None
    id: str = None

    def __post_init__(self):
        if self.args is None:
            self.args = []

        self.description = f"{self.name}{f' {self.html_element}' if self.html_element else ''}, args: {self.args}"


@dataclass
class BrowserTab:
    index: int
    title: str
    url: str
    is_focused: bool
