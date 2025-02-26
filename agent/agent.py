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
        self.model = "o1"
        self.max_retries = 3

        # Agent State
        self.client = AsyncOpenAI()
        self.identity = identity
        self.objective = objective  # The objective of the agent (e.g. "buy a macbook")
        self.message_history: List[Dict[str, Any]] = []

        self.observation_history: List[Dict[str, Any]] = []
        self.planning_history: List[Dict[str, Any]] = []
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
        while True:
            async with self._timed_operation("Observation & Planning"):
                response_json = await self._observe_and_plan_next_action()

            # page_description = response_json["planning"]["page_summary"]
            # captcha_detected = await self._detect_captcha(page_description)
            # if captcha_detected:
            #     print("Captcha detected. Yielding control to human.")
            #     await self._wait_for_human_input()
            #     continue

            action = AgentAction(**response_json["action"])
            self.action_history.append(action)

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
        async with self._timed_operation(f"{model} call"):
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
                "content": content,
            }
        )

    # Main Methods
    async def _observe_and_plan_next_action(self) -> Tuple[str, str]:
        """Observe the page and plan the next action"""
        screenshot_base64 = await self.browser.take_screenshot()

        await self.browser.annotate_page()
        annotated_screenshot_base64 = await self.browser.take_screenshot()

        if not self.message_history:
            self._append_to_history("system", await self._get_system_prompt())

        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_planning_prompt(
                        self.browser.label_simplified_htmls,
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_base64}",
                        "detail": "high",
                    },
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{annotated_screenshot_base64}",
                        "detail": "high",
                    },
                },
            ],
        }

        response = await self._make_llm_call(
            self.message_history + [user_message], self.model
        )

        if len(self.action_history) > 0:
            dummy_user_message = (
                f"Performed the following action: {self.action_history[-1].description}"
            )
            self._append_to_history("user", dummy_user_message)

        self._append_to_history("assistant", response)
        response_json = json.loads(response)
        self.planning_history.append(response_json)
        print(json.dumps(response_json, indent=4))
        return response_json

    async def _execute_action(self, action: AgentAction) -> None:
        """Execute the next action in the plan."""
        await self.browser.clear_annotations()

        try:
            await self.browser.execute_action(action)
            await self.browser.wait_for_page_load()
        except Exception as e:
            print(f"Error executing action: {e}\nTrying again next iteration...")
            # Remove last two messages from history on failure
            self.message_history = self.message_history[:-2]

    # Prompts
    async def _get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        return f"""You are a helpful web browsing assistant. Here is your ultimate objective: {
            self.objective
        }.

POSSIBLE ACTIONS
- CLICK: click a specific element on the page
- TYPE: type text into a text box on the page (only use this if you need to fill out an input box without immediately triggering a form submission)
- TYPE_AND_SUBMIT: type text into a text box on the page and submit (e.g. search bar). Use this when the input field is designed to immediately perform an action upon receiving text.
- EXTRACT: extract information from the page. Only argument should be what the information you want to retrieve from the page.
- SCROLL_DOWN: scroll down on the page.
- SCROLL_UP: scroll up on the page
- GO_BACK: go back to the previous page
- GO_TO: go to a specific url
- REFRESH: refresh the page
- END: declare that you have completed the task


TIPS:
- Use scroll to find elements you are looking for
- If none of the visible elements on the page are appropriate for the action you want to take, try to scroll down the page to see if you can find any.
- If you are stuck, try alternative approaches - like going back to a previous page, new search, new tab etc.
"""

    async def _get_planning_prompt(
        self,
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
                elements_text = f"[Top of page]\n{elements_text}"
            if has_content_below:
                elements_text = f"{elements_text}\n... {pixels_below} pixels below - scroll down to see more ..."
            else:
                elements_text = f"{elements_text}\n[Bottom of page]"
        else:
            elements_text = "None"

        page_position = ""
        if has_content_above and has_content_below:
            page_position = "You are in the middle of the page."
        elif has_content_below:
            page_position = "You are at the top of the page."
        elif has_content_above:
            page_position = "You are at the bottom of the page."

        return f"""CONTEXT:
You are on a page of {self.browser.get_site_name()}. {page_position}

The exact url is {self.browser.page.url}.

The first screenshot is the current state of the page after the previous action was performed.

The second screenshot is the current page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the label of the element. Each label is associated with the simplified html of the element.


Here are the elements you can interact with:
{elements_text}



TASK: Respond with a JSON object with the following fields:
{{
    "planning": {{
        "page_summary": "Detailed summary of key information relevant to the task from the current page which is not yet in the task history memory.",
        "evaluate_previous_action": "Reason about whether the previous action was successful or not.",
        "progress": "Summarize what has been done (since the beginning) and what hasn't been done yet in an abstract way. DO NOT COMMENT ABOUT WHAT ACTIONS YOU ARE GOING TO TAKE. ONLY COMMENT ON WHAT HAS BEEN DONE AND WHAT IS LEFT TO DO.",
        "next_step": "Reason about what is an appropriate next step. Consider a few different options and reason about the pros and cons of each. Ultimately, choose the one that is most likely to lead to the completion of the task."
    }},
    "action" : {{
        "description": "Very short description of the action you want to take.",
        "name": "Action name from the POSSIBLE ACTIONS section.",
        "args": "Arguments needed for the action in a list. If you are interacting with an element, you must provide the element number as the first argument. If you don't need to provide any additional arguments (e.g. you are just scrolling), set the "args" to an empty list. When you are typing text, provide the text you want to type as the second argument."
    }}
}}
"""

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
