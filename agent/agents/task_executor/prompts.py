from agent.agents.utils.prompt_formatting import (
    get_formatted_interactable_elements,
    get_formatted_page_position,
    get_formatted_tabs,
)
from agent.browser.core.browser import AgentBrowser
from agent.models import AgentAction


def get_system_prompt(task: str) -> str:
    return f"""You are a web browsing assistant helping to complete the following task: "{task}"

Here are the possible actions you can take:
- click_element (element_id: int): click on an element on the page
- type_text (element_id: int, text: str): type text into a text box on the page and optionally submit the text
- scroll (direction: up | down, amount: float = 0.75): manually scroll the page in the given direction by the given amount
- scroll_to_content (content_to_find: str): automatically scroll to specific content on the page. Use this if you need to find something that is not currently visible e.g. a button that is not visible. Provide as much context/detail as possible about what you are looking for.
- extract (information_to_extract: str): Performs OCR and extracts textual information from the current page based on a descriptive query of what you are looking for e.g. "recipe and ingredients", "first paragraph", "top comment" etc.
- navigate (direction: back | forward): go back to the previous page or go forward to the next page
- go_to_url (url: str): go to a specific url
- switch_tab (tab_index: int): switch to a different tab
- end_task: declare that you have completed the task


Guidelines:
- Always use the extract action if you need to extract specific information from the page (recipe, top comment, title, etc.), even if you can see the information on the page.
- If you need to find a specific element on the page to interact with (e.g. a button, link, etc.), use the scroll_to_content action instead of the scroll action. Only use the scroll action if you need to view more of the page.
- When performing a search via a search bar, use a more general query if the current query is not working.
"""


async def get_action_choice_prompt(browser: AgentBrowser) -> str:
    """Returns the prompt template for planning the next action"""
    page = browser.current_page
    pixels_above, pixels_below = await page.get_pixels_above_below()
    page_position = get_formatted_page_position(pixels_above, pixels_below)
    page_summary = page.page_summary
    page_breakdown = page.page_breakdown
    interactable_elements = get_formatted_interactable_elements(
        pixels_above, pixels_below, page.elements
    )
    tabs = await get_formatted_tabs(browser)
    return f"""OPEN BROWSER TABS:
{tabs}

PAGE DETAILS:
{page_position}

- Summary:
{page_summary}


- Detailed breakdown:
{page_breakdown}


About the screenshot:
- It shows the current visible portion of the page with bounding boxes drawn around interactable elements.
- The element IDs are the numbers in top-left of boxes.


CURRENTLY VISIBLE INTERACTABLE ELEMENTS:
{interactable_elements}


TASK:
1. Summarize everything you have done so far and what you still need to do.
- Is the objective complete?
- Has all the information requested in the objective been extracted and is present in the message history?


2. Reason about what action to take next.
- Consider the elements you can currently see and interact with on the page.
- Consider what actions you have already tried. Don't repeat actions that aren't working. Find an alternative strategy.
- If the task is complete, respond with the action "end_task".


Finally, respond with a JSON object with the following fields:
{{
    "progress": <summary of what you have done so far and what you still need to do>,
    "reasoning": <reasoning for choosing this action>,
    "action_description": <one sentence description of the action you will perform>,
    "action_name": <name of the action to take>,
    "kwargs": <kwargs for the action>,
}}"""


def get_action_feedback_prompt(action: AgentAction) -> str:
    return f"""Based on the two screenshots, evaluate whether the following action was completed successfully.

Intended action: {action.description}

Action performed: {action.name} {f"(on {action.element.get('description', '')})" if action.element else ""}

The first screenshot is the state of the page before the action, and the second screenshot is the state of the page after the action. Consider what UX changes are expected for the action.
- If no visible change occured, consider why e.g. perhaps the action was selecting on option that was already selected.
- Make sure the intended action was actually completed. 

Output your verdict as a JSON object with the following fields:
{{
    "reasoning": <reasoning about whether the action was completed successfully>,
    "evaluation": <statement about the action's outcome, making sure to restate the action, with a brief explanation of why the action was completed or not>,
}}"""


def get_task_output_prompt(task: str) -> str:
    return f"""TASK 1:            
Provide a 1-2 sentence final response to the task. If the task was not completed, briefly explain why not.

As a reminder, the task is: {task}

TASK 2:
Determine if the task requires any information to be returned. If so, reference the message history to find the requested information and return it. DO NOT MAKE UP ANY INFORMATION. If information requested for the task is not present in the message history, simply state what information is missing.
            

Output your response in JSON format.
{{
    "response": <final response to the task>,
    "reasoning": <reasoning about whether the task requires any information to be returned>,
    "information": <Return the content requested by the task in natural language. If no information is requested, return an empty string>,
}}"""
