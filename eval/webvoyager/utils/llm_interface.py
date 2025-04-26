import asyncio
import json
import os
import time
from typing import Any, Dict, List, Tuple

from openai import AsyncAzureOpenAI, AsyncOpenAI

from .constants import (
    INITIAL_EVALUATION_SYSTEM_PROMPT,
    INITIAL_EVALUATION_USER_PROMPT_TEMPLATE,
    MODEL_PRICING,
    REEVALUATION_PROMPT_TEMPLATE,
)
from .file_io import encode_image
from .parsing import get_extract_message_outputs
from .types import Evaluation, Metadata


def initialize_client(model: str) -> AsyncOpenAI | AsyncAzureOpenAI:
    """Initializes the appropriate OpenAI client based on the model name."""
    if model == "o4-mini":
        return AsyncOpenAI()
    else:
        return AsyncAzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint="https://jonathan-research.openai.azure.com",
        )


def prepare_initial_evaluation_messages(
    metadata: Metadata, process_dir: str, img_num: int
) -> List[Dict[str, Any]]:
    """Prepares the messages list for the initial LLM evaluation call."""
    screenshot_dir = os.path.join(process_dir, "screenshots")
    screenshot_files = sorted(
        [f for f in os.listdir(screenshot_dir) if f.endswith(".png")]
    )

    # Ensure img_num does not exceed available screenshots
    img_num = min(img_num, len(screenshot_files))

    whole_content_img = []
    end_files = screenshot_files[-img_num:]
    for png_file in end_files:
        try:
            b64_img = encode_image(os.path.join(screenshot_dir, png_file))
            whole_content_img.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_img}"},
                }
            )
        except FileNotFoundError:
            print(f"Warning: Screenshot file not found: {png_file} in {screenshot_dir}")
        except Exception as e:
            print(f"Warning: Error encoding image {png_file}: {e}")

    user_prompt_tmp = INITIAL_EVALUATION_USER_PROMPT_TEMPLATE.replace(
        "<task>", metadata["objective"]
    )
    # Ensure final_response is a string
    final_response_str = (
        json.dumps(metadata["final_response"])
        if not isinstance(metadata["final_response"], str)
        else metadata["final_response"]
    )
    user_prompt_tmp = user_prompt_tmp.replace("<answer>", final_response_str)
    user_prompt_tmp = user_prompt_tmp.replace("<num>", str(len(end_files)))

    messages = [
        {"role": "system", "content": INITIAL_EVALUATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [{"type": "text", "text": user_prompt_tmp}]
            + whole_content_img
            + [{"type": "text", "text": "Your verdict:\n"}],
        },
    ]
    return messages


def prepare_reevaluation_prompt(metadata: Metadata) -> str:
    """Prepares the prompt string for the re-evaluation LLM call."""

    # Access initial evaluation data from the new structure
    evaluation_result_data = metadata.get("evaluation_result")
    assert evaluation_result_data is not None
    assert evaluation_result_data.get("evaluation") is not None
    initial_eval_data = evaluation_result_data.get("evaluation")
    eval_reasoning = initial_eval_data.get("explanation")

    message_history = metadata.get("message_history", "")
    final_response = metadata.get("final_response", "N/A")
    objective = metadata.get("objective", "N/A")

    # Ensure final_response is a string
    final_response_str = (
        json.dumps(final_response)
        if not isinstance(final_response, str)
        else final_response
    )

    extract_outputs = get_extract_message_outputs(message_history)
    formatted_extract_outputs = "\n-----------------------------------\n".join(
        extract_outputs
    )

    prompt = REEVALUATION_PROMPT_TEMPLATE.format(
        objective=objective,
        final_response=final_response_str,
        eval_reasoning=eval_reasoning,
        formatted_extract_outputs=formatted_extract_outputs,
    )
    return prompt


async def call_llm(
    client: AsyncOpenAI | AsyncAzureOpenAI,
    model: str,
    messages: List[Dict[str, Any]] | None = None,
    prompt: str | None = None,
    json_mode: bool = True,
) -> Tuple[str, float]:
    """Calls the LLM with retry logic and cost calculation."""
    cost = 0.0
    max_retries = 5
    retry_delay = 10  # seconds

    if messages is None and prompt is None:
        raise ValueError("Either messages or prompt must be provided")
    if messages is not None and prompt is not None:
        raise ValueError("Only one of messages or prompt can be provided")

    if prompt:
        # Convert prompt string to messages format if needed
        messages_to_send = [
            {
                "role": "system",  # Assuming re-evaluation prompt is a system message
                "content": prompt,
            },
        ]
    else:
        messages_to_send = messages

    for attempt in range(max_retries):
        try:
            kwargs: dict[str, Any] = {
                "seed": 42,  # For reproducibility
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            if model.startswith("gpt"):
                kwargs["temperature"] = 0.0
            if model.startswith("o"):
                kwargs["reasoning_effort"] = "high"

            print(f"Calling LLM {model}... (Attempt {attempt + 1}/{max_retries})")
            start_time = time.time()
            openai_response = await client.chat.completions.create(
                model=model,
                messages=messages_to_send,  # type: ignore
                **kwargs,
            )
            end_time = time.time()
            print(f"API call completed in {end_time - start_time:.2f}s")

            if openai_response.usage and model in MODEL_PRICING:
                cost = (
                    openai_response.usage.prompt_tokens
                    * MODEL_PRICING[model]["prompt_tokens"]
                    + openai_response.usage.completion_tokens
                    * MODEL_PRICING[model]["completion_tokens"]
                )
                print(f"Cost for {model}: ${cost:.6f}")
            else:
                print(f"Warning: Could not calculate cost for model {model}")

            if openai_response.choices[0].message.content is None:
                raise ValueError("No response content from LLM")

            response_content = openai_response.choices[0].message.content
            return response_content, cost

        except Exception as e:
            print(f"Error during API call (Attempt {attempt + 1}): {e}")
            error_type = type(e).__name__
            if attempt == max_retries - 1:
                print("Max retries reached. Failing task.")
                raise  # Re-raise the last exception

            if error_type == "RateLimitError":
                print(
                    f"Rate limit exceeded, sleeping for {retry_delay * (attempt + 1)}s..."
                )
                await asyncio.sleep(retry_delay * (attempt + 1))
            elif error_type == "APIError":
                print(
                    f"API error, sleeping for {retry_delay * 1.5 * (attempt + 1)}s..."
                )
                await asyncio.sleep(retry_delay * 1.5 * (attempt + 1))
            elif error_type == "InvalidRequestError":
                print("Invalid request error. Check prompt/parameters. Failing task.")
                raise  # Re-raise immediately for invalid requests
            else:
                print(
                    f"Unhandled error ({error_type}), sleeping for {retry_delay * (attempt + 1)}s..."
                )
                await asyncio.sleep(retry_delay * (attempt + 1))

    # Should not be reached if max_retries > 0, but needed for type checking
    raise Exception("LLM call failed after multiple retries")


def process_llm_response_into_evaluation(
    response_content: str, cost: float, model: str
) -> Evaluation:
    """Parses the LLM response JSON and adds cost/model info."""
    try:
        response = json.loads(response_content)
        if "verdict" not in response or "explanation" not in response:
            raise ValueError(
                "LLM response missing required fields 'verdict' or 'explanation'."
            )
        response["cost"] = cost
        response["model"] = model
        evaluation: Evaluation = response
        return evaluation
    except json.JSONDecodeError as e:
        print(f"Error decoding LLM JSON response: {e}")
        print(f"Raw response: {response_content}")
        raise ValueError("Failed to parse LLM JSON response")
