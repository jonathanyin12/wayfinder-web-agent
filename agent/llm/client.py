from typing import Any, Dict, List

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage


class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI()
        self.max_retries = 3

    async def make_call(
        self,
        messages: List[ChatCompletionMessage],
        model: str,
        tools: List[Dict[str, Any]] = None,
        attempt: int = 0,
    ) -> Dict[str, Any]:
        """Helper method to make LLM API calls with retry logic"""
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                **({"response_format": {"type": "json_object"}} if not tools else {}),
                **({"temperature": 0.0} if model.startswith("gpt-4o") else {}),
                **({"reasoning_effort": "low"} if model.startswith("o") else {}),
                **({"tools": tools} if tools else {}),
                **({"tool_choice": "required"} if tools else {}),
                **({"parallel_tool_calls": False} if tools else {}),
            )
            if tools:
                return response.choices[0].message
            else:
                return response.choices[0].message.content
        except Exception as e:
            if attempt >= self.max_retries - 1:
                raise Exception(f"Failed after {self.max_retries} attempts: {str(e)}")
            print(f"Attempt {attempt + 1} failed with error: {str(e)}")
            return await self.make_call(messages, model, tools, attempt + 1)

    def create_message_with_images(
        self, text_content: str, images: List[str]
    ) -> List[Dict[str, Any]]:
        """Helper to create a message with text and images

        Args:
            text_content: The text content of the message
            images: List of base64-encoded images to include

        Returns:
            A formatted content list ready for OpenAI API
        """
        content = [{"type": "text", "text": text_content}]

        for image_base64 in images:
            if image_base64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high",
                        },
                    }
                )

        return content

    def print_message_history(self, message_history: List[Dict[str, Any]]) -> None:
        """Print the message history for debugging"""
        for message in message_history:
            if isinstance(message, ChatCompletionMessage):
                message = message.model_dump()
            print(f"--- {message['role'].upper()} ---")
            if message["content"]:
                if isinstance(message["content"], list):
                    for content in message["content"]:
                        if content["type"] == "text":
                            print(content["text"])
                        elif content["type"] == "image_url":
                            print("[IMAGE]")
                else:
                    print(message["content"])
            elif message["tool_calls"]:
                print("[TOOL CALLS]")
                for tool_call in message["tool_calls"]:
                    print(tool_call)
