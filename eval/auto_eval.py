import argparse
import base64
import json
import os
import time
from typing import Any

from openai import AzureOpenAI

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
}

SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.
-- If you are not sure whether you should believe the content in the response, you should choose unknown.

You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'success', 'failed', or 'unknown'.

Output a JSON object with the following format:
{
    "reasoning": <evaluation reasoning>,
    "verdict": <success | failed | unknown>
}"""

USER_PROMPT = """TASK: <task>
Result Response: <answer>
<num> screenshots at the end: """


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def auto_eval(process_dir, openai_client, api_model, img_num):
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
            if api_model.startswith("gpt-4o"):
                kwargs["temperature"] = 0.0
            if api_model.startswith("o"):
                kwargs["reasoning_effort"] = "high"
            openai_response = openai_client.chat.completions.create(
                model=api_model,
                messages=messages,
                seed=42,
                **kwargs,
            )

            print("API call complete...")
            # Calculate and store cost
            cost = (
                openai_response.usage.prompt_tokens
                * MODEL_PRICING[api_model]["prompt_tokens"]
                + openai_response.usage.completion_tokens
                * MODEL_PRICING[api_model]["completion_tokens"]
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
    verdict = response["verdict"]
    reasoning = response["reasoning"]

    print("Verdict:", verdict)
    print("Reasoning:", reasoning)

    # Add auto evaluation result to metadata
    metadata["cost"] = round(cost, 4)
    metadata["auto_eval"] = response
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    return verdict, reasoning, cost


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--process_dir", type=str, default="results")

    parser.add_argument("--api_model", default="o1", type=str, help="api model name")
    parser.add_argument("--max_attached_imgs", type=int, default=15)
    args = parser.parse_args()

    client = AzureOpenAI(
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

    for web in webs:
        web_task_res = []
        web_cost = 0  # Track cost per website
        for idx in range(0, 46):
            file_dir = os.path.join(args.process_dir, web + "--" + str(idx))
            metadata_file = os.path.join(file_dir, "metadata.json")
            if os.path.exists(metadata_file):
                with open(metadata_file) as fr:
                    metadata = json.load(fr)

                # Skip if the auto evaluation result is already in the metadata
                if "auto_eval" not in metadata:
                    verdict, reasoning, cost = auto_eval(
                        file_dir, client, args.api_model, args.max_attached_imgs
                    )
                    web_task_res.append(verdict)
                    web_cost += cost
                    total_cost += cost
            else:
                pass
        if web_task_res:
            print(f"\n{web} results:")
            print(f"Total cost: ${web_cost:.4f}")
            print(web_task_res)

    print(f"\nTotal cost for all evaluations: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
