import json
import time
from typing import Any, Dict, List, Tuple

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
        self.model = "o3-mini"
        self.vision_model = "gpt-4o"
        self.message_history: List[Dict[str, Any]] = []

    async def launch(self, url: str = "https://google.com", headless: bool = False):
        await self.browser.launch(url, headless)
        await self.execute_agent_loop()

    async def terminate(self):
        await self.browser.terminate()

    async def _make_llm_call(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        attempt: int = 0,
    ) -> Dict[str, Any]:
        """Helper method to make LLM API calls with retry logic"""
        start_time = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                **({"temperature": 0.0} if model.startswith("gpt-4o") else {}),
                **({"reasoning_effort": "high"} if model == "o3-mini" else {}),
            )
            result = json.loads(response.choices[0].message.content)
            print(f"{model} call took {time.time() - start_time:.2f} seconds")
            return result
        except Exception as e:
            if attempt >= self.max_retries - 1:
                raise Exception(f"Failed after {self.max_retries} attempts: {str(e)}")
            print(f"Attempt {attempt + 1} failed with error: {str(e)}")
            return await self._make_llm_call(messages, model, attempt + 1)

    async def _describe_page(self) -> str:
        """Describe the current page for non-vision models to understand."""
        await self.browser.annotate_page()
        screenshot_base64 = await self.browser.take_screenshot()

        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_page_description_prompt(),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_base64}",
                    },
                },
            ],
        }
        return await self._make_llm_call(
            self.message_history + [user_message], self.vision_model
        )

    async def _observe_and_plan(self) -> Tuple[str, str]:
        """Observe the current state of the browser and plan the next action."""
        page_description = json.dumps(await self._describe_page(), indent=4)
        print(page_description)
        # Append the system prompt only at the beginning.
        if not self.message_history:
            system_message = {
                "role": "system",
                "content": await self._get_system_prompt(),
            }
            self.message_history.append(system_message)

        # Prepare and append the user message.
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_observe_and_plan_prompt(
                        page_description, self.browser.label_simplified_htmls
                    ),
                },
            ],
        }
        self.message_history.append(user_message)

        # Make the LLM call with the complete conversation history.
        response_json = await self._make_llm_call(self.message_history, self.model)

        # Append the assistant's response to the history.
        self.message_history.append(
            {"role": "assistant", "content": json.dumps(response_json)}
        )
        print(json.dumps(response_json, indent=4))
        return response_json["action"], response_json["action_args"]

    async def _execute_agent_action(
        self, action: str, action_args: List[str]
    ) -> Tuple[str, str, str]:
        """Execute the next action in the plan."""
        if len(action_args) > 0:
            label_selector = self.browser.label_selectors[str(action_args[0])]
            print(f"Label selector: {label_selector}")
            text = action_args[1] if len(action_args) > 1 else ""
        else:
            label_selector = None
            text = ""

        await self.browser.clear_annotations()
        try:
            await self.browser.execute_action(action, label_selector, text)
            await self.browser.wait_for_page_load()
        except Exception as e:
            print(f"Error executing action: {e}\nTrying again next iteration...")
            self.message_history = self.message_history[
                :-2
            ]  # Remove last user and assistant messages

    async def _get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        return f"""You are a helpful web browsing assistant. Here is your ultimate objective: {self.objective}.

POSSIBLE ACTIONS
- CLICK: click a specific element on the page
- TYPE: type text into a text box on the page (only use this if you need to fill out an input box without immediately triggering a form submission)
- TYPE_AND_SUBMIT: type text into a text box on the page and submit (e.g. search bar). Use this when the input field is designed to immediately perform an action upon receiving text.
- SCROLL_DOWN: scroll down on the page
- SCROLL_UP: scroll up on the page
- GO_BACK: go back to the previous page
- GO_TO: go to a specific url
- REFRESH: refresh the page
- END: declare that you have completed the task


TASKS
For every response, you must always complete the following tasks
1. What is the next goal that would bring you closer to your objective?
2. Is there currently a visible element on the page that you can interact with to get closer to your objective? If so, what is it? If not, would scrolling up or down help you get closer to your objective? Or should you go to a different page?
3. Output the action you want to take
4. Provide arguments needed for the action in a list. If you are interacting with an element, you must provide the element number as the first argument. If you don't need to provide any additional arguments (e.g. you are just scrolling), set the "action_args" to an empty list. When you are typing text, provide the text you want to type as the second argument.


Respond with a JSON object with the following fields:
{{
    "next_goal": <Task 1>,
    "reasoning": <Task 2>,
    "action": <Task 3>,
    "action_args": <Task 4>,
}}
"""

    async def _get_observe_and_plan_prompt(
        self, page_description: str, label_simplified_htmls: Dict[str, str]
    ) -> str:
        """Returns the prompt template for observation phase"""
        scroll_percentage = await self.browser.get_scroll_percentage()
        if scroll_percentage is not None:
            scroll_percentage_block = f"The page is currently scrolled {scroll_percentage}% from the top (0% = top, 100% = bottom)."
        else:
            scroll_percentage_block = ""
        return f"""You are currently on a specific page of {self.browser.get_site_name()}. The exact url is {self.browser.page.url}. {scroll_percentage_block}

Here is a description of the page:
{page_description}

Here are the visible elements you can interact with:
{json.dumps(label_simplified_htmls, indent=4)}
"""

    async def execute_agent_loop(self):
        """
        Make a plan, execute it, and then review the results.
        """
        while True:
            start_time = time.time()
            action, action_args = await self._observe_and_plan()
            print(
                f"Observation and planning took {time.time() - start_time:.2f} seconds"
            )
            start_time = time.time()
            await self._execute_agent_action(action, action_args)
            print(f"Execution took {time.time() - start_time:.2f} seconds")

    async def _get_page_description_prompt(self) -> str:
        """Returns the prompt template for observation phase"""
        scroll_percentage = await self.browser.get_scroll_percentage()
        if scroll_percentage is not None:
            scroll_percentage_block = f"The page is currently scrolled {scroll_percentage}% from the top (0% = top, 100% = bottom)."
        else:
            scroll_percentage_block = ""
        return f"""You are currently on a specific page of {self.browser.get_site_name()}. The exact url is {self.browser.page.url}.

The page is annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the label of the element. If something doesn't have a bounding box around it, you cannot interact with it. Each label is associated with the simplified html of the element.

{scroll_percentage_block}


Describe the page in detail. Use context clues from both the image and previous conversation to help you figure out what the page is about. Output a JSON object with the following fields:
{{
    "key_content": <Description of the key content>,
    "page_overview": <One sentence summary of the page and its purpose>,
}}
"""
