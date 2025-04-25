import json
from dataclasses import dataclass, field
from typing import Any

from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)


@dataclass
class AgentAction:
    name: str
    element: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    reasoning: str = ""
    tool_call: ChatCompletionMessageToolCall | None = None

    def __str__(self):
        args = self.args.copy()
        args.pop("element_id", None)
        if self.element:
            return f"Action: {self.name}\nElement: {json.dumps(self.element, indent=4)}\nArgs: {json.dumps(args, indent=4)}"
        else:
            return f"Action: {self.name}\nArgs: {json.dumps(self.args, indent=4)}"


@dataclass
class BrowserTab:
    index: int
    title: str
    url: str
    is_focused: bool
