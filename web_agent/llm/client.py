from typing import Any, Dict, List, Literal, Optional, Union

from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion_content_part_image_param import (
    ChatCompletionContentPartImageParam,
    ImageURL,
)
from openai.types.chat.chat_completion_content_part_text_param import (
    ChatCompletionContentPartTextParam,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

PRICING = {
    "gpt-4o-mini": {
        "prompt_tokens": 0.15 / 1000000,
        "completion_tokens": 0.6 / 1000000,
    },
    "gpt-4o": {
        "prompt_tokens": 2.5 / 1000000,
        "completion_tokens": 10 / 1000000,
    },
    "gpt-4.1-mini": {
        "prompt_tokens": 0.4 / 1000000,
        "completion_tokens": 1.6 / 1000000,
    },
    "gpt-4.1": {
        "prompt_tokens": 2 / 1000000,
        "completion_tokens": 8 / 1000000,
    },
    "o1": {
        "prompt_tokens": 15 / 1000000,
        "completion_tokens": 60 / 1000000,
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


class LLMClient:
    global_token_usage = {}

    def __init__(self):
        self.client = AsyncAzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint="https://jonathan-research.openai.azure.com",
        )
        self.oai_client = AsyncOpenAI()
        self.max_retries = 3
        self.token_usage = {}

    async def make_call(
        self,
        messages: List[ChatCompletionMessageParam],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        attempt: int = 0,
        timeout: int = 120,
        json_format: bool = True,
        reasoning_effort: Optional[Literal["low", "medium", "high"]] = "high",
    ) -> ChatCompletionMessage:
        """Helper method to make LLM API calls with retry logic"""
        if model == "o4-mini":
            client = self.oai_client
        else:
            client = self.client
        try:
            kwargs = {}
            if json_format and not tools:
                kwargs["response_format"] = {"type": "json_object"}
            if model.startswith("gpt"):
                kwargs["temperature"] = 0.0
            if model.startswith("o"):
                kwargs["reasoning_effort"] = reasoning_effort
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "required"
                if model.startswith("gpt"):
                    kwargs["parallel_tool_calls"] = False

            response = await client.with_options(
                timeout=timeout
            ).chat.completions.create(model=model, messages=messages, **kwargs)

            # Track token usage by model
            if model not in self.token_usage:
                self.token_usage[model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

            if model not in LLMClient.global_token_usage:
                LLMClient.global_token_usage[model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

            # Update token counts
            usage = response.usage
            self.token_usage[model]["prompt_tokens"] += usage.prompt_tokens
            self.token_usage[model]["completion_tokens"] += usage.completion_tokens
            self.token_usage[model]["total_tokens"] += usage.total_tokens

            LLMClient.global_token_usage[model]["prompt_tokens"] += usage.prompt_tokens
            LLMClient.global_token_usage[model]["completion_tokens"] += (
                usage.completion_tokens
            )
            LLMClient.global_token_usage[model]["total_tokens"] += usage.total_tokens

            return response.choices[0].message
        except Exception as e:
            if attempt >= self.max_retries - 1:
                raise Exception(f"Failed after {self.max_retries} attempts: {str(e)}")
            print(
                f"Attempt {attempt + 1} failed with error: {str(e)}. Model: {model}, Timeout: {timeout}"
            )
            return await self.make_call(
                messages, model, tools, attempt + 1, timeout, json_format
            )

    def get_token_usage(self) -> Dict[str, Dict[str, int]]:
        """Get the current token usage statistics for all models

        Returns:
            A dictionary with token usage statistics by model
        """
        return self.token_usage

    def get_total_cost(self) -> float:
        """Get the total cost of all token usage"""
        return sum(
            usage["prompt_tokens"] * PRICING[model]["prompt_tokens"]
            + usage["completion_tokens"] * PRICING[model]["completion_tokens"]
            for model, usage in self.token_usage.items()
        )

    def print_token_usage(self, global_usage: bool = False) -> None:
        """Print the current token usage statistics for all models"""
        print("\n=== TOKEN USAGE STATISTICS ===")

        if global_usage:
            token_usage = LLMClient.global_token_usage
        else:
            token_usage = self.token_usage

        for model, usage in token_usage.items():
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
            for model, usage in token_usage.items()
        )
        print(f"Total cost: ${total_cost:.6f}")

    def create_user_message_with_images(
        self,
        text_content: str,
        images: List[str],
        detail: Optional[
            Union[Literal["auto", "low", "high"], List[Literal["auto", "low", "high"]]]
        ] = None,
    ) -> ChatCompletionUserMessageParam:
        """Helper to create a message with text and images

        Args:
            text_content: The text content of the message
            images: List of base64-encoded images to include
            detail: Either a single detail level or list of detail levels ('auto', 'low', or 'high')

        Returns:
            A formatted message ready for OpenAI API
        """
        content: List[
            Union[
                ChatCompletionContentPartTextParam, ChatCompletionContentPartImageParam
            ]
        ] = []
        if text_content:
            content.append(
                ChatCompletionContentPartTextParam(type="text", text=text_content)
            )
        if detail is None:
            details: List[Literal["auto", "low", "high"]] = ["high"] * len(images)
        else:
            # If detail is a single string, convert it to a list
            if isinstance(detail, str):
                details = [detail] * len(images)  # type: ignore
            # If detail is a list, check its length
            else:
                assert len(detail) == len(images)
                details = detail

        for image_base64, detail in zip(images, details):
            if image_base64:
                content.append(
                    ChatCompletionContentPartImageParam(
                        type="image_url",
                        image_url=ImageURL(
                            url=f"data:image/png;base64,{image_base64}",
                            detail=detail,
                        ),
                    )
                )

        return ChatCompletionUserMessageParam(role="user", content=content)

    def format_message_history(
        self, message_history: List[Dict[str, Any] | ChatCompletionMessageParam]
    ) -> str:
        """Format the message history into a readable string for debugging

        Args:
            message_history: List of message dictionaries

        Returns:
            A formatted string representation of the message history
        """
        formatted_output = []

        for message in message_history:
            # Convert ChatCompletionMessage to dict if needed
            if isinstance(message, ChatCompletionMessage):
                message = message.model_dump()

            # Add a clear header for each message
            role = message.get("role", "UNKNOWN").upper()
            formatted_output.append(f"=== {role} MESSAGE ===")

            # Process message content
            content = message.get("content")
            if content is not None:
                if isinstance(content, list):
                    # Handle multi-part content (text and images)
                    for content_item in content:
                        if content_item.get("type") == "text":
                            # Format text content with indentation
                            text_lines = content_item.get("text", "").split("\n")
                            for line in text_lines:
                                formatted_output.append(f"  {line}")
                        elif content_item.get("type") == "image_url":
                            formatted_output.append("  [IMAGE ATTACHMENT]")
                else:
                    # Handle simple string content
                    text_lines = str(content).split("\n")
                    for line in text_lines:
                        formatted_output.append(f"  {line}")

            # Handle tool calls
            tool_calls = message.get("tool_calls")
            if tool_calls:
                formatted_output.append("  [TOOL CALLS]")
                for i, tool_call in enumerate(tool_calls, 1):
                    formatted_output.append(f"  Tool Call #{i}:")
                    formatted_output.append(f"    {tool_call}")

            # Add separator between messages
            formatted_output.append("")
            formatted_output.append("-" * 50)
            formatted_output.append("")

        return "\n".join(formatted_output)

    def print_message_history(
        self, message_history: List[Union[Dict[str, Any], ChatCompletionMessageParam]]
    ) -> None:
        """Print the message history for debugging"""
        formatted_history = self.format_message_history(message_history)
        print(formatted_history)
