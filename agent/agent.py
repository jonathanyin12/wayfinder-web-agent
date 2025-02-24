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

        self.observation_history: List[Dict[str, Any]] = []
        self.planning_history: List[Dict[str, Any]] = []

        # Browser Setup
        self.human_control = False
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
            if self.human_control:
                await self._wait_for_human_input()

            async with self._timed_operation("Observation"):
                page_description = await self._observe_page()
            captcha_detected = await self._detect_captcha(page_description)
            if captcha_detected:
                print("Captcha detected. Yielding control to human.")
                await self._yield_control_to_human()
                continue

            async with self._timed_operation("Planning"):
                action, action_args = await self._plan_next_action(page_description)

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

    # Main Methods
    async def _observe_page(self) -> str:
        """Describe the current page for non-vision models to understand."""
        screenshot_base64 = await self.browser.take_screenshot()

        is_new_page = self.browser.is_new_page()

        content = [
            {
                "type": "text",
                "text": await self._get_page_description_prompt(is_new_page),
            }
        ]

        if not is_new_page:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{self.browser.previous_page_screenshot_base64}",
                    },
                }
            )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{screenshot_base64}",
                },
            }
        )

        user_message = {
            "role": "user",
            "content": content,
        }
        page_description_json = await self._make_llm_call(
            self.message_history + [user_message], self.vision_model
        )
        self.observation_history.append(page_description_json)
        print(json.dumps(page_description_json, indent=4))
        return json.dumps(page_description_json, indent=4)

    async def _plan_next_action(self, page_description: str) -> Tuple[str, str]:
        """Plan the next action based on the page description"""
        await self.browser.annotate_page()
        if not self.message_history:
            self._append_to_history("system", await self._get_system_prompt())

        is_new_page = self.browser.is_new_page()
        print(json.dumps(self.browser.label_simplified_htmls, indent=4))

        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_planning_prompt(
                        is_new_page,
                        page_description,
                        self.browser.label_simplified_htmls,
                    ),
                }
            ],
        }
        self._append_to_history("user", user_message["content"])

        response_json = await self._make_llm_call(self.message_history, self.model)
        self._append_to_history("assistant", response_json)
        self.planning_history.append(response_json)
        print(json.dumps(response_json, indent=4))
        return response_json["action"], response_json["action_args"]

    def _parse_action_config(self, action: str, action_args: List[str]) -> ActionConfig:
        """Parse action and arguments into a config object"""
        if not action_args:
            return ActionConfig(action=action)

        # Get the selector and use it directly
        label_selector = self.browser.label_selectors[str(action_args[0])]

        text = action_args[1] if len(action_args) > 1 else ""
        return ActionConfig(action=action, label_selector=label_selector, text=text)

    async def _execute_action(self, action: str, action_args: List[str]) -> None:
        """Execute the next action in the plan."""
        config = self._parse_action_config(action, action_args)

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

    # Prompts
    async def _get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        return f"""You are a helpful web browsing assistant. Here is your ultimate objective: {self.objective}.

POSSIBLE ACTIONS
- CLICK: click a specific element on the page
- TYPE: type text into a text box on the page (only use this if you need to fill out an input box without immediately triggering a form submission)
- TYPE_AND_SUBMIT: type text into a text box on the page and submit (e.g. search bar). Use this when the input field is designed to immediately perform an action upon receiving text.
- SCROLL_DOWN: scroll down on the page.
- SCROLL_UP: scroll up on the page
- GO_BACK: go back to the previous page
- GO_TO: go to a specific url
- REFRESH: refresh the page
- END: declare that you have completed the task


TASKS
For every response, you must always complete the following tasks
1. Reflect on whether the last action you took ({self.planning_history[-1]["action_description"] if self.planning_history else "N/A"}) successfully achieved your previous strategic goal. If the page did not change as a result of the action, does not look as expected, or the action was not successful, the action was not successful.
2. What is your next high-level goal? This should be a high-level outcome (like "Add the laptop to cart") rather than a specific action (like "Click the search button" or "Click add to cart"). If you haven't achieved your previous goal, you can keep the same goal unless there's a compelling reason to change it.
3. Is there currently a visible element on the page that you can interact with to get closer to your objective? If so, what is it? If not, would scrolling up or down help you get closer to your objective? Or should you go to a different page?
4. Concisely describe the action you want to take in a way that is easy for a human to understand.
5. Output the action you want to take
6. Provide arguments needed for the action in a list. If you are interacting with an element, you must provide the element number as the first argument. If you don't need to provide any additional arguments (e.g. you are just scrolling), set the "action_args" to an empty list. When you are typing text, provide the text you want to type as the second argument.


TIPS:
- Use scroll to find elements you are looking for
- If none of the visible elements on the page are appropriate for the action you want to take, try to scroll down the page to see if you can find any.
- If you are stuck, try alternative approaches - like going back to a previous page, new search, new tab etc.


Respond with a JSON object with the following fields:
{{
    "previous_action_evaluation": <Task 1>,
    "goal": <Task 2>,
    "reasoning": <Task 3>,
    "action_description": <Task 4>,
    "action": <Task 5>,
    "action_args": <Task 6>,
}}
"""

    async def _get_page_description_prompt(self, is_new_page: bool) -> str:
        """Returns the prompt template for observation phase"""
        if is_new_page:
            return f"""You are currently on a specific page of {self.browser.get_site_name()}. The exact url is {self.browser.page.url}.

Describe the page in detail. Use context clues from both the image and previous conversation to help you figure out what the page is about. Output a JSON object with the following fields:
{{
    "key_content": <Description of the key content>,
    "page_overview": <One sentence summary of the page and its purpose>,
}}
"""

        return f"""You are currently on a specific page of {self.browser.get_site_name()}. The exact url is {self.browser.page.url}.

The last action you took on the page was: {self.planning_history[-1]["action_description"] if self.planning_history else "N/A"}

You are given two screenshots of the page. The first screenshot is the state of the page before your last action. The second screenshot is of the current state of the page.


Describe what has happened on the page since the previous screenshot. This will be used to evaluate whether your last action was successful. Use context clues from both the image and your last action to help you figure out what the page is about. Output a JSON object with the following fields:
{{
    "page_changes": <Description of the differences between the two screenshots>,
    "key_content": <Description of the key content on the current state of the page>,
    "page_overview": <One sentence summary of the current state of the page and its purpose>,
}}
"""

    async def _get_planning_prompt(
        self,
        is_new_page: bool,
        page_description: str,
        label_simplified_htmls: Dict[str, str],
    ) -> str:
        """Returns the prompt template for planning the next action"""
        pixels_above, pixels_below = await self.browser.get_pixels_above_below()

        has_content_above = pixels_above > 0
        has_content_below = pixels_below > 0

        elements_text = json.dumps(label_simplified_htmls, indent=4)
        if elements_text:
            if has_content_above:
                elements_text = f"... {pixels_above} pixels above - scroll up to see more ...\n{elements_text}"
            else:
                elements_text = f"[Start of page]\n{elements_text}"
            if has_content_below:
                elements_text = f"{elements_text}\n... {pixels_below} pixels below - scroll down to see more ..."
            else:
                elements_text = f"{elements_text}\n[End of page]"
        else:
            elements_text = "None"

        if is_new_page:
            return f"""You are currently on a new page of {self.browser.get_site_name()}. The exact url is {self.browser.page.url}.

Here is a description of the page:
{page_description}

Here are the visible elements you can interact with:
{elements_text}
"""
        return f"""You are on the same page of {self.browser.get_site_name()}. The exact url is {self.browser.page.url}.

Here is a description of how the page has changed as a result of your last action:
{page_description}

Here are the visible elements you can interact with:
{elements_text}
"""

    # Human Control Methods
    async def _yield_control_to_human(self):
        """Yield control back to human"""
        self.human_control = True

    async def _wait_for_human_input(self):
        """Wait for human to press Enter to yield control back to agent"""
        while True:
            user_input = input(
                "Press 'Enter' when you want to yield control back to the agent."
            )
            if user_input == "":  # Empty string means Enter was pressed
                self.human_control = False
                print("Yielding control back to the agent.")
                break
            print("Please press 'Enter' key only.")

    async def _detect_captcha(self, page_description: str) -> bool:
        """Detect if a captcha is present on the page by simply checking if the description of the page contains the word 'captcha'"""
        return "captcha" in page_description.lower()
