from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentAction:
    name: str
    html_element: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self):
        self.description = f"{self.name}{f' {self.html_element}' if self.html_element else ''}, args: {self.args}"


@dataclass
class BrowserTab:
    index: int
    title: str
    url: str
    is_focused: bool
