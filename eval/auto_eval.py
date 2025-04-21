import argparse
import asyncio
import base64
import json
import os
import time
from typing import Any

from openai import AsyncAzureOpenAI, AsyncOpenAI

MODEL_PRICING = {
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
    "gpt-4.1": {
        "prompt_tokens": 2 / 1000000,
        "completion_tokens": 8 / 1000000,
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
- YOU SHOULD ONLY CHOOSE 'FAILED' IF YOU HAVE EXPLICIT EVIDENCE THAT THE TASK WAS NOT COMPLETED SUCCESSFULLY.


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


async def auto_eval(process_dir, openai_client, model, img_num):
    print(f"--------------------- {process_dir} ---------------------")
    cost = 0  # Initialize cost for this evaluation

    metadata_file = os.path.join(process_dir, "metadata.json")
    with open(metadata_file) as fr:
        metadata = json.load(fr)

    # Get the screenshots from the screenshots directory
    screenshot_dir = os.path.join(process_dir, "screenshots")
    screenshot_files = sorted(
        [f for f in os.listdir(screenshot_dir) if f.endswith(".png")]
    )

    # Initialize the list to store image content
    whole_content_img = []

    # Get the last img_num screenshots
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
    while True:
        try:
            kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}}
            if model.startswith("gpt"):
                kwargs["temperature"] = 0.0
            if model.startswith("o"):
                kwargs["reasoning_effort"] = "high"
            openai_response = await openai_client.chat.completions.create(
                model=model,
                messages=messages,
                seed=42,
                **kwargs,
            )

            print("API call complete...")
            # Calculate and store cost
            cost = (
                openai_response.usage.prompt_tokens
                * MODEL_PRICING[model]["prompt_tokens"]
                + openai_response.usage.completion_tokens
                * MODEL_PRICING[model]["completion_tokens"]
            )
            print("Cost:", cost)
            break
        except Exception as e:
            print(e)
            if type(e).__name__ == "RateLimitError":
                time.sleep(10)
            elif type(e).__name__ == "APIError":
                time.sleep(15)
            elif type(e).__name__ == "InvalidRequestError":
                exit(0)
            else:
                time.sleep(10)
    response = openai_response.choices[0].message.content

    response = json.loads(response)
    response["eval_cost"] = cost
    response["eval_model"] = model
    verdict = response["verdict"]
    reasoning = response["explanation"]

    print("Verdict:", verdict)
    print("Explanation:", reasoning)

    # Add auto evaluation result to metadata
    metadata["auto_eval"] = response
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    return verdict, reasoning, cost


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output_dir",
        type=str,
    )
    parser.add_argument("--model", default="o4-mini", type=str, help="api model name")
    parser.add_argument("--max_attached_imgs", type=int, default=15)
    args = parser.parse_args()

    if args.model == "o4-mini":
        client = AsyncOpenAI()
    else:
        client = AsyncAzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint="https://jonathan-research.openai.azure.com",
        )
    webs = [
        "Allrecipes",
        "Amazon",
        "Apple",
        "ArXiv",
        "BBC News",
        "Booking",
        "Cambridge Dictionary",
        "Coursera",
        "ESPN",
        "GitHub",
        "Google Flights",
        "Google Map",
        "Google Search",
        "Huggingface",
        "Wolfram Alpha",
    ]
    total_cost = 0  # Initialize total cost tracker
    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(20)

    from collections import defaultdict

    from tqdm.asyncio import tqdm_asyncio

    async def process_task(file_dir, client, model, max_attached_imgs):
        async with semaphore:
            return await auto_eval(file_dir, client, model, max_attached_imgs)

    all_tasks = []
    # Collect all tasks that need to be run across all websites
    print("Collecting tasks...")
    for web in webs:
        for idx in range(0, 46):
            file_dir = os.path.join(args.output_dir, web + "--" + str(idx))
            metadata_file = os.path.join(file_dir, "metadata.json")
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file) as fr:
                        metadata = json.load(fr)
                    # Skip if the auto evaluation result is already in the metadata
                    # if "auto_eval" not in metadata:
                    task = process_task(
                        file_dir, client, args.model, args.max_attached_imgs
                    )
                    all_tasks.append({"task": task, "file_dir": file_dir, "web": web})
                except json.JSONDecodeError:
                    print(
                        f"Warning: Could not decode JSON from {metadata_file}. Skipping."
                    )
                except Exception as e:
                    print(f"Warning: Error processing {file_dir}: {e}. Skipping.")

    results_by_web = defaultdict(list)
    costs_by_web = defaultdict(float)

    # Run all tasks concurrently if any tasks were collected
    if all_tasks:
        print(f"Running {len(all_tasks)} tasks concurrently...")
        results = await tqdm_asyncio.gather(
            *(item["task"] for item in all_tasks), desc="Processing all tasks"
        )

        # Process results and aggregate by website
        for result_data, task_info in zip(results, all_tasks):
            verdict, reasoning, cost = result_data
            web = task_info["web"]
            results_by_web[web].append(verdict)
            costs_by_web[web] += cost
            total_cost += cost
    else:
        print("No tasks to run.")

    # Print results per website
    print("\n--- Evaluation Results ---")
    for web in webs:
        if web in results_by_web:
            print(f"\n{web} results:")
            print(f"Total cost: ${costs_by_web[web]:.4f}")
            print(results_by_web[web])
        else:
            print(f"\n{web}: No new tasks were processed.")

    print(f"\nTotal cost for all evaluations: ${total_cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
