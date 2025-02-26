from typing import Any, Dict


class PromptManager:
    def __init__(self, objective: str):
        self.objective = objective

    async def get_system_prompt(self, pixels_above: int, pixels_below: int) -> str:
        """Returns the system prompt for the agent"""
        scroll_down = (
            "\n - SCROLL_DOWN: scroll down on the page." if pixels_below > 0 else ""
        )
        scroll_up = "\n - SCROLL_UP: scroll up on the page." if pixels_above > 0 else ""

        return f"""You are a helpful web browsing assistant. 
        
Here is your ultimate objective: {self.objective}.

POSSIBLE ACTIONS:
- CLICK: click a specific element on the page
- TYPE: type text into a text box on the page (only use this if you need to fill out an input box without immediately triggering a form submission)
- TYPE_AND_SUBMIT: type text into a text box on the page and submit (e.g. search bar). Use this when the input field is designed to immediately perform an action upon receiving text.
- EXTRACT: extract information from the page. Only argument should be the extraction task (e.g. "summarize the reviews of the product on the page"){scroll_down}{scroll_up}
- GO_BACK: go back to the previous page
- GO_TO: go to a specific url
- END: declare that you have completed the task


TIPS:
- Use scroll to find elements you are looking for
- If none of the visible elements on the page are appropriate for the action you want to take, try to scroll down the page to see if you can find any.
- If you are stuck, try alternative approaches, like going back to a previous page, new search, new tab etc. DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING.
"""

    async def get_planning_prompt(
        self,
        site_name: str,
        page_position: str,
        url: str,
        interactable_elements: str,
        last_action_description: str = None,
    ) -> str:
        """Returns the prompt template for planning the next action"""
        if not last_action_description:
            return f"""CONTEXT:
You are on a page of {site_name}. {page_position}

The exact url is {url}.

The screenshot is the current state of the page.

Here are the elements you can interact with:
{interactable_elements}


TASK:
1. Provide a detailed summary of key information relevant to the task from the current page.

2. Reason about what is an appropriate next step given the current state of the page and the overall objective.

Respond with a JSON object with the following fields:
{{
    "page_summary": <Task 1>,
    "next_step": <Task 2>
}}
"""
        return f"""CONTEXT:
You are on a page of {site_name}. {page_position}

The exact url is {url}.

The first screenshot is the state of the page before the last action was performed.

The second screenshot is the current state of the page, after the last action was performed.

Here are the elements you can interact with:
{interactable_elements}


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

    async def get_action_prompt(
        self,
        site_name: str,
        page_position: str,
        url: str,
        interactable_elements: str,
        next_step: Dict[str, Any],
    ) -> str:
        """Returns the prompt template for planning the next action"""
        return f"""CONTEXT:
You are on a page of {site_name}. {page_position}

The exact url is {url}.

The first screenshot is the current state of the page after the last action was performed.

The second screenshot is the current page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the label of the element. Each label is associated with the simplified html of the element.


Here are the elements you can interact with:
{interactable_elements}


TASK: 
Choose the action that best matches the following next step:
{next_step}

Respond with a JSON object with the following fields:
{{
    "name": "Action name from the POSSIBLE ACTIONS section.",
    "description": "A very short description of the action you are taking.",
    "args": "Arguments needed for the action in a list. If you are interacting with an element, you must provide the element number as the first argument. If you don't need to provide any additional arguments (e.g. you are just scrolling), set the "args" to an empty list. When you are typing text, provide the text you want to type as the second argument."
}}"""
