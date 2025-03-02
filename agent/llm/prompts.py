import json
from typing import Any, Dict, List

from agent.models import AgentAction, BrowserTab


class PromptManager:
    def __init__(self, objective: str):
        self.objective = objective

    def get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        return f"""You are a helpful web browsing assistant.    
        
Here is your ultimate objective: {self.objective}.

POSSIBLE ACTIONS:
- click_element: click a specific element on the page
- type_text: type text into a text box on the page and optionally submit the text
- extract_info: extract specific information from the page
- scroll: scroll up or down on the page
- navigate: go back to the previous page or go forward to the next page
- go_to_url: go to a specific url
- switch_tab: switch to a different tab
- end: declare that you have completed the task
"""

    async def get_planning_prompt(
        self,
        browser,
        last_action: AgentAction | None = None,
    ) -> str:
        page = browser.pages[browser.current_page_index]

        pixels_above, pixels_below = await page.get_pixels_above_below()
        page_position = get_formatted_page_position(pixels_above, pixels_below)
        interactable_elements = get_formatted_interactable_elements(
            pixels_above, pixels_below, page.label_simplified_htmls
        )
        base_url = page.get_base_url()
        shortened_url = page.get_shortened_url()
        tabs = await get_formatted_tabs(browser)
        """Returns the prompt template for planning the next action"""
        if not last_action:
            return f"""CONTEXT:
You are on a page of {base_url}. {page_position}

The exact url is {shortened_url}.

The screenshot is the current state of the page.

Available tabs:
{tabs}


Here are the elements you can interact with (element_id: element_html):
{interactable_elements}


TASK:
1. Provide a brief summary of key information relevant to the task from the current page.

2. Suggest anappropriate next step given the current state of the page and the overall objective.

Respond with a JSON object with the following fields:
{{
    "page_summary": <Task 1>,
    "next_step": <Task 2>
}}
"""
        return f"""CONTEXT:
You are on a page of {base_url}. {page_position}

The exact url is {shortened_url}.

The last action you performed was: {last_action.description}

The first screenshot is the state of the page before the last action was performed.

The second screenshot is the current state of the page, after the last action was performed.


Here are the available tabs:
{tabs}


Here are the elements you can interact with (element_id: element_html):
{interactable_elements}


TASK:
1. Provide a brief summary of new key information relevant to the task from the current page. 

2. Reason about whether the last action was successful or not.
- Carefully compare the before and after screenshots to verify whether the action was successful. Consider what UX changes are expected for the action you took.
- If an action is not successful, try to reason about what went wrong and what you can do differently. e.g. if you clicked on an element but it didn't change state, it may have already been selected or in the desired state. If you tried to scroll but the page didn't move, it may be the end of the page or the page is not scrollable.

3. Summarize what has been accomplished since the beginning. Also, broadly describe what else is remaining of the overall objective.

4. Suggest an appropriate next step given the current state of the page and the overall objective.
- Think in terms of potential short action sequences rather than broad goals. The actions you can take are listed under POSSIBLE ACTIONS.
- If you are stuck, try alternative approaches. DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING. 
- If the objective is complete, suggest ending the task.

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
        browser,
        next_step: Dict[str, Any],
    ) -> str:
        """Returns the prompt template for planning the next action"""
        page = browser.pages[browser.current_page_index]
        pixels_above, pixels_below = await page.get_pixels_above_below()
        page_position = get_formatted_page_position(pixels_above, pixels_below)
        interactable_elements = get_formatted_interactable_elements(
            pixels_above, pixels_below, page.label_simplified_htmls
        )
        base_url = page.get_base_url()
        shortened_url = page.get_shortened_url()
        tabs = await get_formatted_tabs(browser)
        return f"""CONTEXT:
You are on a page of {base_url}. {page_position}

The exact url is {shortened_url}.

The first screenshot is the current state of the page after the last action was performed.

The second screenshot is the current page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the id of the element. Each id is associated with the simplified html of the element.


Here are the elements you can interact with (element_id: element_html):
{interactable_elements}


Here are the available tabs:
{tabs}


TASK: 
Choose the action that best matches the following next step:
{next_step}

The entire next step may not be achievable through a single action and may require multiple actions (e.g. scroll down first, then click on an element). If so, simply output the first action. If no currently visible elements are relevant to the next step, scrolling may be required to reveal the relevant elements.
"""


def get_formatted_interactable_elements(
    pixels_above, pixels_below, label_simplified_htmls
) -> str:
    """
    Get a formatted string of interactable elements on the page.

    Args:
        page: The Playwright page
        label_simplified_htmls: Dictionary of labeled HTML elements
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A formatted string representation of interactable elements
    """
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

    return elements_text


def get_formatted_page_position(pixels_above, pixels_below) -> str:
    """
    Get a formatted string describing the current scroll position.

    Args:
        pixels_above_below: Tuple containing (pixels_above, pixels_below)

    Returns:
        A human-readable description of the current scroll position
    """
    has_content_above = pixels_above > 0
    has_content_below = pixels_below > 0

    if has_content_above and has_content_below:
        page_position = "You are in the middle of the page."
    elif has_content_above:
        page_position = "You are at the bottom of the page."
    elif has_content_below:
        page_position = "You are at the top of the page."
    else:
        page_position = "The entire page is visible. No scrolling is needed/possible."

    return page_position


async def get_formatted_tabs(browser) -> List[BrowserTab]:
    """
    Get a formatted string of tabs in the browser.
    """
    tabs = []
    for i, page in enumerate(browser.pages):
        tabs.append(
            BrowserTab(
                index=i,
                title=await page.page.title(),
                url=page.get_shortened_url(),
                is_focused=browser.current_page_index == i,
            )
        )
    return tabs
