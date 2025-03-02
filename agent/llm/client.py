from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

PRICING = {
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
}


class LLMClient:
    # Class-level dictionary to track token usage globally across all instances
    token_usage = {}

    def __init__(self):
        self.client = AsyncOpenAI()
        self.max_retries = 3

    async def make_call(
        self,
        messages: List[ChatCompletionMessage],
        model: str,
        tools: List[Dict[str, Any]] = None,
        attempt: int = 0,
        timeout: int = 60,
        json_format: bool = True,
    ) -> Dict[str, Any]:
        """Helper method to make LLM API calls with retry logic"""
        try:
            response = await self.client.with_options(
                timeout=timeout
            ).chat.completions.create(
                model=model,
                messages=messages,
                **(
                    {"response_format": {"type": "json_object"}}
                    if json_format and not tools
                    else {}
                ),
                **({"temperature": 0.0} if model.startswith("gpt-4o") else {}),
                **({"reasoning_effort": "high"} if model.startswith("o") else {}),
                **({"tools": tools} if tools else {}),
                **({"tool_choice": "required"} if tools else {}),
                **({"parallel_tool_calls": False} if tools else {}),
            )

            # Track token usage by model
            if model not in LLMClient.token_usage:
                LLMClient.token_usage[model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

            # Update token counts
            usage = response.usage
            LLMClient.token_usage[model]["prompt_tokens"] += usage.prompt_tokens
            LLMClient.token_usage[model]["completion_tokens"] += usage.completion_tokens
            LLMClient.token_usage[model]["total_tokens"] += usage.total_tokens

            if tools:
                return response.choices[0].message
            else:
                return response.choices[0].message.content
        except Exception as e:
            if attempt >= self.max_retries - 1:
                raise Exception(f"Failed after {self.max_retries} attempts: {str(e)}")
            print(f"Attempt {attempt + 1} failed with error: {str(e)}")
            return await self.make_call(messages, model, tools, attempt + 1)

    @classmethod
    def get_token_usage(cls) -> Dict[str, Dict[str, int]]:
        """Get the current token usage statistics for all models

        Returns:
            A dictionary with token usage statistics by model
        """
        return cls.token_usage

    @classmethod
    def print_token_usage(cls) -> None:
        """Print the current token usage statistics for all models"""
        print("\n=== TOKEN USAGE STATISTICS ===")
        for model, usage in cls.token_usage.items():
            print(f"Model: {model}")
            print(f"  Prompt tokens: {usage['prompt_tokens']}")
            print(f"  Completion tokens: {usage['completion_tokens']}")
            print(f"  Total tokens: {usage['total_tokens']}")
            print(
                f"  Cost: ${usage['prompt_tokens'] * PRICING[model]['prompt_tokens'] + usage['completion_tokens'] * PRICING[model]['completion_tokens']:.6f}"
            )
            print("----------------------------")
        total_cost = sum(
            usage["prompt_tokens"] * PRICING[model]["prompt_tokens"]
            + usage["completion_tokens"] * PRICING[model]["completion_tokens"]
            for model, usage in cls.token_usage.items()
        )
        print(f"Total cost: ${total_cost:.6f}")

    def create_user_message_with_images(
        self,
        text_content: str,
        images: List[str],
        detail: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Helper to create a message with text and images

        Args:
            text_content: The text content of the message
            images: List of base64-encoded images to include

        Returns:
            A formatted content list ready for OpenAI API
        """
        content = [{"type": "text", "text": text_content}]
        if detail is None:
            details = ["high"] * len(images)
        else:
            # If detail is a single string, convert it to a list
            if isinstance(detail, str):
                details = [detail] * len(images)
            # If detail is a list, check its length
            elif isinstance(detail, list):
                assert len(detail) == len(images)
                details = detail

        for image_base64, detail in zip(images, details):
            if image_base64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": detail,
                        },
                    }
                )

        return {"role": "user", "content": content}

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
