from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentAction:
    name: str
    element: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    description: str = ""
    reasoning: str = ""


@dataclass
class BrowserTab:
    index: int
    title: str
    url: str
    is_focused: bool
