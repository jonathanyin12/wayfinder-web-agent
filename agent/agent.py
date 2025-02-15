import json
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .browser import AgentBrowser

load_dotenv()


class Agent:
    def __init__(self, identity: str = "", objective: str = ""):
        self.client = AsyncOpenAI()
        self.identity = identity
        self.browser = AgentBrowser()
        self.objective = objective  # The objective of the agent (e.g. "buy a macbook")
        self.max_retries = 3
        self.model = "gpt-4o"

    async def launch(self, url: str = "https://google.com", headless: bool = False):
        await self.browser.launch(url, headless)
        await self.execute_agent_loop()

    async def terminate(self):
        await self.browser.terminate()

    async def _make_llm_call(self, messages: list, attempt: int = 0) -> Dict[str, Any]:
        """Helper method to make LLM API calls with retry logic"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            if attempt >= self.max_retries - 1:
                raise Exception(f"Failed after {self.max_retries} attempts: {str(e)}")
            print(f"Attempt {attempt + 1} failed with error: {str(e)}")
            return await self._make_llm_call(messages, attempt + 1)

    async def _observe_and_plan(self) -> Tuple[str, str]:
        """Observe the current state of the browser and plan the next action."""
        screenshot_base64 = await self.browser.take_screenshot()
        messages = [
            {
                "role": "system",
                "content": f"You are a helpful assistant. Here is your objective: {self.objective}.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": self._get_observe_and_plan_prompt(),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}",
                        },
                    },
                ],
            },
        ]

        response_json = await self._make_llm_call(messages)
        print(json.dumps(response_json, indent=4))
        return response_json["observation"], response_json["reasoning"]

    async def _execute_agent_action(self, reasoning: str) -> Tuple[str, str, str]:
        """Execute the next action in the plan."""
        label_selectors, label_simplified_htmls = await self.browser.annotate_page()
        screenshot_base64 = await self.browser.take_screenshot()
        await self.browser.clear_annotations()

        messages = [
            {
                "role": "system",
                "content": f"You are a helpful assistant. Here is your objective: {self.objective}.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": self._get_action_prompt(
                            reasoning, label_simplified_htmls
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}",
                        },
                    },
                ],
            },
        ]

        response_json = await self._make_llm_call(messages)
        print(json.dumps(response_json, indent=4))

        label = str(response_json["element_number"])
        label_selector = label_selectors[label]

        await self.browser.execute_action(
            response_json["action_name"],
            label_selector,
            response_json["action_args"],
        )
        return label, response_json["action_name"], response_json["action_args"]

    def _get_observe_and_plan_prompt(self) -> str:
        """Returns the prompt template for observation phase"""
        return f"""You are currently on a specific page of {self.browser.get_site_name()}, which shown in the image.

Your end goal is to complete the following objective: {self.objective}.

TASKS:
1. Decribe what you see in the screenshot. 
2. Reason about what you should do next on the page to get closer to your objective.

Output your response in a JSON object with the following fields:
{{
    "observation": <Task 1>,
    "reasoning": <Task 2>,
}}"""

    def _get_action_prompt(self, reasoning: str, label_simplified_htmls: Dict) -> str:
        """Returns the prompt template for action phase"""
        return f"""Your end goal is to complete the following objective: {self.objective}.

You are currently on a specific page of {self.browser.get_site_name()}, which shown in the image. The page is annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the label of the element. If something doesn't have a bounding box around it, you cannot interact with it. Each label is associated with the simplified html of the element.

Here are the elements you can interact with shown in the image:
{json.dumps(label_simplified_htmls, indent=4)}

Here is the next action you planned to take to get closer to your objective: {reasoning}.

TASKS:
1. Output the label of the element you want to interact with according to your plan.
2. Choose the appropriate action to take on the element based on your plan.

Here are the following actions you can take on a page:
- CLICK: click a specific element on the page
- TYPE: type text into a text input or textarea
- TYPE_AND_SUBMIT: type text into a text input or textarea and press enter
- SCROLL_DOWN: scroll down on the page
- SCROLL_UP: scroll up on the page
- GO_BACK: go back to the previous page
- GO_TO: go to a specific url
- REFRESH: refresh the page
- END: declare that you have completed the task

3. (Optional) Provide any additional arguments needed for the action. If you don't need to provide any additional arguments, set the "action_args" to an empty string.

Output your response in a JSON object with the following fields:
{{
    "element_number": <Task 1>,
    "action_name": <Task 2>,
    "action_args": <Task 3>,
}}"""

    async def execute_agent_loop(self):
        """
        Make a plan, execute it, and then review the results.
        """
        while True:
            observation, reasoning = await self._observe_and_plan()

            await self._execute_agent_action(reasoning)
