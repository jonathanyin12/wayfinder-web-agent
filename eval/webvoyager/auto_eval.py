import argparse
import asyncio
import base64
import json
import os
import time
from typing import Any, Dict, List, Tuple

from aggregate_results import aggregate_results
from openai import AsyncAzureOpenAI, AsyncOpenAI
from tqdm.asyncio import tqdm_asyncio
from utils import MODEL_PRICING, TaskData

SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Screenshots: This is a visual representation of the screen showing the process of performing a web task. It serves as visual proof of the actions taken in response to the instruction. The screenshots are ordered in chronological order.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.


Your primary responsibility is to evaluate the task completion by:
1. Assessing whether the actions shown in screenshots and described in the response align with the web task instructions
2. Verifying that all conditions and parts of the instructions were met and completed successfully
3. Using screenshots as the definitive source of truth when explicit contradictions exist with the text response. The text response not being present in the screenshots is not a contradiction.

Note: The person performing the task is able to extract textual information from the page without scrolling to it first. As a result, it's possible some information they gathered in the result response cannot be verified through the screenshots.

Rules:
- IF THERE'S NO EVIDENCE IN THE SCREENSHOTS TO VERIFY THE INFORMATION IN THE RESULT RESPONSE, YOU SHOULD CHOOSE 'UNCLEAR'.
- IF YOU HAVE EXPLICIT EVIDENCE THAT THE TASK WAS NOT COMPLETED SUCCESSFULLY, YOU SHOULD CHOOSE 'FAILED'
- IF THE PERSON PERFORMING THE TASK CHALLENGES THE FEASIBILITY OF THE TASK, YOU SHOULD CHOOSE 'FAILED'
- IF THE PERSON PERFORMING THE TASK SAID THEY DID NOT COMPLETE THE TASK, YOU SHOULD CHOOSE 'FAILED'


Provide detailed feedback explaining:
- For successful tasks: Why the task was completed correctly
- For failed tasks: What went wrong and what should have been done differently
- For unclear verdicts: What information was missing to make a determination


Output a JSON object with the following format:
{
    "verdict": <success | failed | unclear>
    "explanation": <explanation>
}"""

USER_PROMPT = """TASK: <task>
Result Response: <answer>
The last <num> screenshots are attached. """


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _load_task_metadata(process_dir: str) -> Dict[str, Any]:
    """Loads metadata from the metadata.json file."""
    metadata_file = os.path.join(process_dir, "metadata.json")
    with open(metadata_file) as fr:
        return json.load(fr)


def _prepare_evaluation_prompt(
    metadata: Dict[str, Any], process_dir: str, img_num: int
) -> List[Dict[str, Any]]:
    """Prepares the messages list for the LLM evaluation call."""
    screenshot_dir = os.path.join(process_dir, "screenshots")
    screenshot_files = sorted(
        [f for f in os.listdir(screenshot_dir) if f.endswith(".png")]
    )

    whole_content_img = []
    end_files = screenshot_files[-img_num:]
    for png_file in end_files:
        b64_img = encode_image(os.path.join(screenshot_dir, png_file))
        whole_content_img.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_img}"},
            }
        )

    user_prompt_tmp = USER_PROMPT.replace("<task>", metadata["objective"])
    if not isinstance(metadata["final_response"], str):
        metadata["final_response"] = json.dumps(metadata["final_response"])
    user_prompt_tmp = user_prompt_tmp.replace("<answer>", metadata["final_response"])
    user_prompt_tmp = user_prompt_tmp.replace("<num>", str(img_num))

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [{"type": "text", "text": user_prompt_tmp}]
            + whole_content_img
            + [{"type": "text", "text": "Your verdict:\n"}],
        },
    ]
    return messages


async def _call_evaluation_llm(
    client: Any, model: str, messages: List[Dict[str, Any]]
) -> Tuple[str, float]:
    """Calls the LLM for evaluation with retry logic and cost calculation."""
    cost = 0.0
    while True:
        try:
            kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}}
            if model.startswith("gpt"):
                kwargs["temperature"] = 0.0
            if model.startswith("o"):
                kwargs["reasoning_effort"] = "high"
            openai_response = await client.chat.completions.create(
                model=model,
                messages=messages,
                seed=42,
                **kwargs,
            )

            print("API call complete...")
            if openai_response.usage:
                cost = (
                    openai_response.usage.prompt_tokens
                    * MODEL_PRICING[model]["prompt_tokens"]
                    + openai_response.usage.completion_tokens
                    * MODEL_PRICING[model]["completion_tokens"]
                )
                print("Cost:", cost)

            if openai_response.choices[0].message.content is None:
                raise Exception("No response from LLM")

            response_content = openai_response.choices[0].message.content
            return response_content, cost

        except Exception as e:
            print(f"Error during API call: {e}")
            error_type = type(e).__name__
            if error_type == "RateLimitError":
                print("Rate limit exceeded, sleeping for 10s...")
                time.sleep(10)
            elif error_type == "APIError":
                print("API error, sleeping for 15s...")
                time.sleep(15)
            elif error_type == "InvalidRequestError":
                print("Invalid request error. Exiting.")
                # Consider raising the exception or handling it differently
                # For now, re-raising to stop execution for this task
                raise
            else:
                print(f"Unhandled error ({error_type}), sleeping for 10s...")
                time.sleep(10)


def _process_llm_response(
    response_content: str, cost: float, model: str
) -> Dict[str, Any]:
    """Parses the LLM response JSON and adds cost/model info."""
    response = json.loads(response_content)
    response["eval_cost"] = cost
    response["eval_model"] = model
    return response


def _save_evaluation_result(
    process_dir: str, metadata: Dict[str, Any], evaluation_result: Dict[str, Any]
):
    """Saves the evaluation result back to the metadata file."""
    metadata["auto_eval"] = evaluation_result
    metadata_file = os.path.join(process_dir, "metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)


async def evaluate_task(
    semaphore: asyncio.Semaphore,
    process_dir: str,
    openai_client: Any,
    model: str,
    img_num: int,
) -> Tuple[str, str, float]:
    """Evaluates a single task by orchestrating helper functions."""
    async with semaphore:
        print(f"--------------------- {process_dir} ---------------------")
        try:
            metadata = _load_task_metadata(process_dir)
            messages = _prepare_evaluation_prompt(metadata, process_dir, img_num)
            response_content, cost = await _call_evaluation_llm(
                openai_client, model, messages
            )
            evaluation_result = _process_llm_response(response_content, cost, model)

            verdict = evaluation_result["verdict"]
            reasoning = evaluation_result["explanation"]
            print("Verdict:", verdict)
            print("Explanation:", reasoning)

            _save_evaluation_result(process_dir, metadata, evaluation_result)

            return verdict, reasoning, cost

        except FileNotFoundError:
            print(f"Metadata file not found in {process_dir}. Skipping task.")
            # Return default values or raise an error, depending on desired behavior
            return "error", f"Metadata file not found: {process_dir}", 0.0
        except json.JSONDecodeError:
            print(f"Invalid JSON in metadata file for {process_dir}. Skipping task.")
            return "error", f"Invalid JSON in metadata: {process_dir}", 0.0
        except Exception as e:
            # Catching broader exceptions that might occur during the process
            print(f"An unexpected error occurred while processing {process_dir}: {e}")
            # Decide on appropriate return values for general errors
            return "error", f"Unexpected error: {e}", 0.0


def initialize_client(model: str):
    """Initializes the appropriate OpenAI client based on the model name."""
    if model == "o4-mini":
        return AsyncOpenAI()
    else:
        return AsyncAzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint="https://jonathan-research.openai.azure.com",
        )


def load_task_definitions(file_path: str) -> List[TaskData]:
    """Loads task definitions from a JSONL file."""
    tasks = []
    with open(file_path, "r") as f:
        for line in f:
            tasks.append(json.loads(line))
    return tasks


async def collect_tasks_to_evaluate(
    output_dir: str,
    tasks: List[TaskData],
    client: Any,  # Using Any because type hint depends on model
    model: str,
    max_attached_imgs: int,
    semaphore: asyncio.Semaphore,
) -> List[asyncio.Task]:
    """Collects tasks that need to be evaluated."""
    all_tasks_to_run = []
    print("Collecting tasks...")
    for task_data in tasks:
        task_id = task_data["id"]
        file_dir = os.path.join(output_dir, task_id)
        metadata_file = os.path.join(file_dir, "metadata.json")

        if not os.path.exists(metadata_file):
            print(f"Skipping {file_dir} because metadata file does not exist.")
            continue

        try:
            with open(metadata_file) as fr:
                metadata = json.load(fr)
            # Skip if the auto evaluation result is already in the metadata
            if "auto_eval" not in metadata:
                task = asyncio.create_task(
                    evaluate_task(semaphore, file_dir, client, model, max_attached_imgs)
                )
                all_tasks_to_run.append(task)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {metadata_file}. Skipping.")
        except Exception as e:
            print(f"Warning: Error processing {file_dir}: {e}. Skipping.")

    return all_tasks_to_run


async def main(results_dir: str, model: str, max_attached_imgs: int):
    client = initialize_client(model)
    tasks = load_task_definitions("benchmark/WebVoyager_cleaned_tasks.jsonl")

    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(20)

    tasks_to_run = await collect_tasks_to_evaluate(
        f"runs/{results_dir}", tasks, client, model, max_attached_imgs, semaphore
    )

    if not tasks_to_run:
        print("No tasks to run.")
        return []

    print(f"Running {len(tasks_to_run)} tasks concurrently...")
    await tqdm_asyncio.gather(*tasks_to_run, desc="Processing all tasks")

    aggregate_results(results_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "results_dir",
        type=str,
    )
    parser.add_argument("--model", default="o4-mini", type=str, help="api model name")
    parser.add_argument("--max_attached_imgs", type=int, default=15)
    args = parser.parse_args()

    asyncio.run(main(args.results_dir, args.model, args.max_attached_imgs))
