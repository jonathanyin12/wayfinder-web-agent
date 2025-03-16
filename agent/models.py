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


@dataclass
class BrowserTab:
    index: int
    title: str
    url: str
    is_focused: bool
