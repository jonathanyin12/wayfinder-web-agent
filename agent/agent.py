import contextlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .browser import AgentBrowser
from .models import AgentAction

load_dotenv()


class Agent:
    # Configuration and Initialization
    def __init__(self, identity: str = "", objective: str = ""):
        self.action_model = "gpt-4o"
        self.planning_model = "o1"
        self.max_retries = 3

        # Agent State
        self.client = AsyncOpenAI()
        self.identity = identity
        self.objective = objective  # The objective of the agent (e.g. "buy a macbook")
        self.message_history: List[Dict[str, Any]] = []

        self.action_history: List[Dict[str, Any]] = []

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
        print(f"BEGINNING TASK: {self.objective}")
        while True:
            # self._print_message_history(self.message_history)

            async with self._timed_operation("Planning"):
                planning_response = await self._plan_next_action()
                print(json.dumps(planning_response, indent=4))

            page_description = planning_response["page_summary"]
            captcha_detected = await self._detect_captcha(page_description)
            if captcha_detected:
                print("Captcha detected. Yielding control to human.")
                await self._wait_for_human_input()
                continue

            next_step = planning_response["next_step"]
            async with self._timed_operation("Choosing action"):
                action = await self._choose_next_action(next_step)
                print(action)

            if action.name == "END":
                print("Completed task. Exiting...")
                break

            async with self._timed_operation("Execution"):
                await self._execute_action(action)

    # LLM  Methods
    async def _make_llm_call(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        attempt: int = 0,
    ) -> Dict[str, Any]:
        """Helper method to make LLM API calls with retry logic"""
        # async with self._timed_operation(f"{model} call"):
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                **({"temperature": 0.0} if model.startswith("gpt-4o") else {}),
                **({"reasoning_effort": "low"} if model.startswith("o") else {}),
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt >= self.max_retries - 1:
                raise Exception(f"Failed after {self.max_retries} attempts: {str(e)}")
            print(f"Attempt {attempt + 1} failed with error: {str(e)}")
            return await self._make_llm_call(messages, model, attempt + 1)

    def _append_to_history(self, role: str, content: Any):
        """Helper method to append messages to history"""
        self.message_history.append(
            {
                "role": role,
                "content": content,
            }
        )

    # Main Methods
    async def _plan_next_action(self) -> Tuple[str, str]:
        """Evaluate the current page and plan the next action"""

        content = [
            {
                "type": "text",
                "text": await self._get_planning_prompt(),
            }
        ]
        if self.browser.previous_page_screenshot_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{self.browser.previous_page_screenshot_base64}",
                        "detail": "high",
                    },
                }
            )
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{self.browser.current_page_screenshot_base64}",
                    "detail": "high",
                },
            }
        )

        user_message = {
            "role": "user",
            "content": content,
        }
        messages = [
            await self._get_system_message(),
            *self.message_history,
            user_message,
        ]
        response = await self._make_llm_call(messages, self.planning_model)

        response_json = json.loads(response)

        formatted_response = f"""Page summary: {response_json["page_summary"]}"""
        if "previous_action_evaluation" in response_json:
            formatted_response = f"{formatted_response}\n\nPrevious action outcome: {response_json['previous_action_evaluation']}"
        if "progress" in response_json:
            formatted_response = (
                f"{formatted_response}\n\nProgress: {response_json['progress']}"
            )
        formatted_response = (
            f"{formatted_response}\n\nNext step: {response_json['next_step']}"
        )

        self._append_to_history("user", formatted_response)
        return response_json

    async def _choose_next_action(
        self,
        next_step: str,
    ) -> AgentAction:
        """Choose the next action to take"""
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_action_prompt(next_step),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{self.browser.current_page_screenshot_base64}",
                        "detail": "high",
                    },
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{self.browser.current_annotated_page_screenshot_base64}",
                        "detail": "high",
                    },
                },
            ],
        }
        messages = [
            await self._get_system_message(),
            user_message,
        ]
        response = await self._make_llm_call(messages, self.action_model)
        response_json = json.loads(response)
        self._append_to_history("assistant", response)

        action = AgentAction(**response_json, description=next_step)
        self.action_history.append(action)
        return action

    async def _execute_action(self, action: AgentAction) -> None:
        """Execute the next action in the plan."""
        try:
            await self.browser.execute_action(action)
        except Exception as e:
            print(f"Error executing action: {e}\nTrying again next iteration...")
            # Remove last two messages from history on failure
            self.message_history = self.message_history[:-2]

    # Prompts
    async def _get_system_message(self) -> Dict[str, Any]:
        """Returns the system message for the agent"""
        return {
            "role": "system",
            "content": await self._get_system_prompt(),
        }

    async def _get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        pixels_above, pixels_below = await self.browser.get_pixels_above_below()
        return f"""You are a helpful web browsing assistant. 
        
Here is your ultimate objective: {self.objective}.

POSSIBLE ACTIONS:
- CLICK: click a specific element on the page
- TYPE: type text into a text box on the page (only use this if you need to fill out an input box without immediately triggering a form submission)
- TYPE_AND_SUBMIT: type text into a text box on the page and submit (e.g. search bar). Use this when the input field is designed to immediately perform an action upon receiving text.
- EXTRACT: extract information from the page. Only argument should be the extraction task (e.g. "summarize the reviews of the product on the page"){"\n - SCROLL_DOWN: scroll down on the page." if pixels_below > 0 else ""}{"\n - SCROLL_UP: scroll up on the page." if pixels_above > 0 else ""}
- GO_BACK: go back to the previous page
- GO_TO: go to a specific url
- END: declare that you have completed the task


TIPS:
- Use scroll to find elements you are looking for
- If none of the visible elements on the page are appropriate for the action you want to take, try to scroll down the page to see if you can find any.
- If you are stuck, try alternative approaches, like going back to a previous page, new search, new tab etc. DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING.
"""

    async def _get_planning_prompt(self) -> str:
        """Returns the prompt template for planning the next action"""
        if len(self.action_history) == 0:
            return f"""CONTEXT:
You are on a page of {self.browser.get_site_name()}. {await self.browser.get_formatted_page_position()}

The exact url is {self.browser.page.url}.

The screenshot is the current state of the page.

Here are the elements you can interact with:
{await self.browser.get_formatted_interactable_elements()}



TASK:
1. Provide a detailed summary of key information relevant to the task from the current page.

2. Reason about what is an appropriate next step given the current state of the page and the overall objective.

Respond with a JSON object with the following fields:
{{
    "page_summary": <Task 1>,
    "next_step": <Task 2>
}}
"""
        last_action = self.action_history[-1]
        last_action_description = last_action.description
        return f"""CONTEXT:
You are on a page of {self.browser.get_site_name()}. {await self.browser.get_formatted_page_position()}

The exact url is {self.browser.page.url}.

The first screenshot is the state of the page before the last action was performed.

The second screenshot is the current state of the page, after the last action was performed.

Here are the elements you can interact with:
{await self.browser.get_formatted_interactable_elements()}


TASK:
1. Provide a detailed summary of key information relevant to the task from the current page which is not yet in the task history memory.

2. Reason about whether the previous action ("{last_action_description}") was successful or not. Carefully compare the before and after screenshots to verify whether the action was successful. Consider what UX changes are expected for the action you took.

3. Summarize what has been accomplished since the beginning. Also, broadly describe what else is remaining of the overall objective.

4. Reason about what is an appropriate next step given the current state of the page and the overall objective. If you are stuck, try alternative approaches. DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING. This must be achievable in a single action, so avoid something that require multiple actions like first scrolling then clicking.

Respond with a JSON object with the following fields:
{{
    "page_summary": <Task 1>,
    "previous_action_evaluation": <Task 2>,
    "progress": <Task 3>,
    "next_step": <Task 4>
}}
"""

    async def _get_action_prompt(
        self,
        next_step: Dict[str, Any],
    ) -> str:
        """Returns the prompt template for planning the next action"""

        return f"""CONTEXT:
You are on a page of {self.browser.get_site_name()}. {await self.browser.get_formatted_page_position()}

The exact url is {self.browser.page.url}.

The first screenshot is the current state of the page after the last action was performed.

The second screenshot is the current page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the label of the element. Each label is associated with the simplified html of the element.


Here are the elements you can interact with:
{await self.browser.get_formatted_interactable_elements()}



TASK: 
Choose the action that best matches the following next step:
{next_step}

Respond with a JSON object with the following fields:
{{
    "name": "Action name from the POSSIBLE ACTIONS section.",
    "args": "Arguments needed for the action in a list. If you are interacting with an element, you must provide the element number as the first argument. If you don't need to provide any additional arguments (e.g. you are just scrolling), set the "args" to an empty list. When you are typing text, provide the text you want to type as the second argument."
}}"""

    # Human Control Methods

    async def _wait_for_human_input(self):
        """Wait for human to press Enter to yield control back to agent"""
        while True:
            user_input = input(
                "Press 'Enter' when you want to yield control back to the agent."
            )
            if user_input == "":  # Empty string means Enter was pressed
                print("Yielding control back to the agent.")
                break
            print("Please press 'Enter' key only.")

    async def _detect_captcha(self, page_description: str) -> bool:
        """Detect if a captcha is present on the page by simply checking if the description of the page contains the word 'captcha'"""
        return "captcha" in page_description.lower()

    def _print_message_history(self, message_history: List[Dict[str, Any]]):
        for message in message_history:
            print(message["role"].upper())
            if isinstance(message["content"], list):
                for content in message["content"]:
                    if content["type"] == "text":
                        print(content["text"])
                    elif content["type"] == "image_url":
                        print("image")
            else:
                print(message["content"])
