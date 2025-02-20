import contextlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .browser import AgentBrowser

load_dotenv()


@dataclass
class ActionConfig:
    action: str
    label_selector: Optional[str] = None
    text: str = ""


class Agent:
    # Configuration and Initialization
    def __init__(self, identity: str = "", objective: str = ""):
        self.model = "o3-mini"
        self.vision_model = "gpt-4o"
        self.max_retries = 3

        # Agent State
        self.client = AsyncOpenAI()
        self.identity = identity
        self.objective = objective  # The objective of the agent (e.g. "buy a macbook")
        self.message_history: List[Dict[str, Any]] = []

        # Browser Setup
        self.browser = AgentBrowser()

    @contextlib.asynccontextmanager
    async def _timed_operation(self, description: str):
        """Context manager for timing operations"""
        start_time = time.time()
        yield
        print(f"{description} took {time.time() - start_time:.2f} seconds")

    # Main Control Flow Methods
    async def launch(self, url: str = "https://google.com", headless: bool = False):
        await self.browser.launch(url, headless)
        await self.execute_agent_loop()

    async def terminate(self):
        await self.browser.terminate()

    async def execute_agent_loop(self):
        """Main agent loop: observe, plan, and execute actions."""
        while True:
            async with self._timed_operation("Observation and planning"):
                action, action_args = await self._plan_next_action()

            async with self._timed_operation("Execution"):
                await self._execute_action(action, action_args)

    # LLM  Methods
    async def _make_llm_call(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        attempt: int = 0,
    ) -> Dict[str, Any]:
        """Helper method to make LLM API calls with retry logic"""
        async with self._timed_operation(f"{model} call"):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    **({"temperature": 0.0} if model.startswith("gpt-4o") else {}),
                    **({"reasoning_effort": "high"} if model == "o3-mini" else {}),
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                if attempt >= self.max_retries - 1:
                    raise Exception(
                        f"Failed after {self.max_retries} attempts: {str(e)}"
                    )
                print(f"Attempt {attempt + 1} failed with error: {str(e)}")
                return await self._make_llm_call(messages, model, attempt + 1)

    def _append_to_history(self, role: str, content: Any):
        """Helper method to append messages to history"""
        self.message_history.append(
            {
                "role": role,
                "content": content if isinstance(content, str) else json.dumps(content),
            }
        )

    async def _plan_next_action(self) -> Tuple[str, str]:
        """Observe the current state and plan the next action."""
        page_description = json.dumps(await self._get_page_description(), indent=4)
        print(page_description)

        if not self.message_history:
            self._append_to_history("system", await self._get_system_prompt())

        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_planning_prompt(
                        page_description, self.browser.label_simplified_htmls
                    ),
                }
            ],
        }
        self._append_to_history("user", user_message["content"])

        response_json = await self._make_llm_call(self.message_history, self.model)
        self._append_to_history("assistant", response_json)
        print(json.dumps(response_json, indent=4))
        return response_json["action"], response_json["action_args"]

    def _parse_action_config(self, action: str, action_args: List[str]) -> ActionConfig:
        """Parse action and arguments into a config object"""
        if not action_args:
            return ActionConfig(action=action)

        label_selector = self.browser.label_selectors[str(action_args[0])]
        text = action_args[1] if len(action_args) > 1 else ""
        return ActionConfig(action=action, label_selector=label_selector, text=text)

    async def _execute_action(self, action: str, action_args: List[str]) -> None:
        """Execute the next action in the plan."""
        config = self._parse_action_config(action, action_args)

        if config.label_selector:
            print(f"Label selector: {config.label_selector}")

        await self.browser.clear_annotations()
        try:
            await self.browser.execute_action(
                config.action, config.label_selector, config.text
            )
            await self.browser.wait_for_page_load()
        except Exception as e:
            print(f"Error executing action: {e}\nTrying again next iteration...")
            # Remove last two messages from history on failure
            self.message_history = self.message_history[:-2]

    # Browser Interaction Methods
    async def _get_page_description(self) -> str:
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

    # Prompts
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

    async def _get_planning_prompt(
        self, page_description: str, label_simplified_htmls: Dict[str, str]
    ) -> str:
        """Returns the prompt template for planning the next action"""
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
