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
        self.model = "gpt-4o"
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
            # self._print_message_history(self.message_history)

            async with self._timed_operation("Evaluation & Planning"):
                eval_planning_response = await self._evaluate_and_plan_next_action()
                print(json.dumps(eval_planning_response, indent=4))

            # page_description = eval_planning_response["page_summary"]
            # captcha_detected = await self._detect_captcha(page_description)
            # if captcha_detected:
            #     print("Captcha detected. Yielding control to human.")
            #     await self._wait_for_human_input()
            #     continue

            async with self._timed_operation("Choose next action"):
                action = await self._choose_next_action(eval_planning_response)
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
                **({"reasoning_effort": "high"} if model.startswith("o") else {}),
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
    async def _evaluate_and_plan_next_action(self) -> Tuple[str, str]:
        """Evaluate the current page and plan the next action"""

        content = [
            {
                "type": "text",
                "text": await self._get_evaluation_planning_prompt(),
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
        response = await self._make_llm_call(messages, self.model)

        response_json = json.loads(response)

        formatted_response = f"""Goal: {response_json["next_goal"]}"""

        if "evaluation" in response_json:
            formatted_response = (
                f"{response_json['evaluation']}\n\n{formatted_response}"
            )

        self._append_to_history("user", formatted_response)
        self.planning_history.append(response_json)
        return response_json

    async def _choose_next_action(
        self,
        eval_planning_response: Dict[str, Any],
    ) -> AgentAction:
        """Choose the next action to take"""
        await self.browser.annotate_page()
        annotated_screenshot_base64 = await self.browser.take_screenshot()

        # print(json.dumps(self.browser.label_simplified_htmls, indent=4))
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": await self._get_action_prompt(
                        eval_planning_response,
                        self.browser.label_simplified_htmls,
                    ),
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
                        "url": f"data:image/png;base64,{annotated_screenshot_base64}",
                        "detail": "high",
                    },
                },
            ],
        }
        messages = [
            await self._get_system_message(),
            *self.message_history[:-1],
            user_message,
        ]
        response = await self._make_llm_call(messages, self.model)
        response_json = json.loads(response)
        self._append_to_history("assistant", response)

        action = AgentAction(**response_json)
        self.action_history.append(action)
        return action

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

    async def _get_evaluation_planning_prompt(self) -> str:
        """Returns the prompt template for planning the next action"""

        if len(self.action_history) == 0:
            return f"""TASK:
Suggest the next goal that will help you achieve your ultimate objective. This should be a short sentence of phrase.
            
You are currently on a page of {self.browser.get_site_name()}, as shown in the image below.

The exact url is {self.browser.page.url}.

Respond with a JSON object with the following field:
{{
    "next_goal": <response>
}}
"""
        last_action = self.action_history[-1]
        last_action_description = last_action.description
        return f"""TASK:
1. Analyze whether the last action you attempted was successful by carefully comparing the before and after screenshots:

The last action you attempted: {last_action_description}

You are on a page of {self.browser.get_site_name()}. 

The exact url is {self.browser.page.url}.

The first image is the page BEFORE the last action was attempted.
The second image is the current state of the page, after the last action was attempted.


First, let's check the intended goal:
- What was the action trying to achieve?
- What would success look like for this specific action?

Next, let's examine visual changes:
- What differences can we see between the before and after screenshots?
- Are these changes what we would expect from a successful action?

Then, let's verify the outcome:
- For clicks: Did the expected UI changes occur? (e.g. new page load, modal opening)
- For navigation: Does the URL and page content match our destination?
- For form submission: Do we see success indicators or error messages?
- For data extraction: Is the target information visible and accessible?
- For scrolling: Has the viewport moved as expected?

Finally, let's assess overall success:
- Based on all the evidence above, did the action achieve its goal?
- If not, what specifically went wrong?
- Are there any unexpected side effects we should note?

Show your work in a step by step manner.
        
2. If your last action was unsuccessful, reason about why it was unsuccessful. Otherwise, output "n/a".

3. If the current goal is not fully complete, set the next goal as the remaining steps needed to complete the goal. If the goal is complete, suggest a next goal that will help you achieve your ultimate objective. If you realize that the goal is impossible, suggest an alternative goal. If you are stuck, try alternative approaches. DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING.


Respond with a JSON object with the following fields:
{{
    "evaluation": <task 1>,
    "failure_reason": <task 2>,
}}
"""

    async def _get_action_prompt(
        self,
        eval_planning_response: Dict[str, Any],
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

        if has_content_above and has_content_below:
            page_position = "You are in the middle of the page. You can scroll up or down to see more."
        elif has_content_above:
            page_position = (
                "You are at the top of the page. You can scroll down to see more."
            )
        elif has_content_below:
            page_position = (
                "You are at the bottom of the page. You can scroll up to see more."
            )
        else:
            page_position = ""

        next_goal = f"[Next goal]\n{eval_planning_response['next_goal']}"

        if "evaluation" in eval_planning_response:
            evaluation = (
                f"[Feedback on the last action]\n{eval_planning_response['evaluation']}"
            )
        else:
            evaluation = ""

        return f"""TASK:
Choose the most appropriate action to take that gets you closer to achieving the following goal:
{next_goal}


{evaluation}


Respond with a JSON object with the following fields:
{{
    "description": "Very short description of the action you want to take.",
    "name": "Action name from the POSSIBLE ACTIONS section.",
    "args": "Arguments needed for the action in a list. If you are interacting with an element, you must provide the element number as the first argument. If you don't need to provide any additional arguments (e.g. you are just scrolling), set the "args" to an empty list. When you are typing text, provide the text you want to type as the second argument."
}}



CONTEXT:
You are on a page of {self.browser.get_site_name()}. 
{page_position}

The exact url is {self.browser.page.url}.

The first screenshot is the original page. 

The second screenshot is the page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the label of the element. If something doesn't have a bounding box around it, you cannot interact with it. Each label is associated with the simplified html of the element.


Here are the visible elements you can interact with:
{elements_text}

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
