from datetime import datetime

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
- type_text (element_id: int, text: str): type text into a text box on the page. This will automatically focus on the text box and clear the text box before typing, so you don't need to click on the text box first or clear it.
- scroll (direction: up | down, amount: float = 0.75): manually scroll the page in the given direction by the given amount
- navigate (direction: back | forward): go back to the previous page or go forward to the next page
- go_to_url (url: str): go to a specific url
- switch_tab (tab_index: int): switch to a different tab
- find (content_to_find: str): search the page for specific content and automatically scrolls to its location if found. Provide as much context/detail as possible about what you are looking for.
- extract (information_to_extract: str): Performs OCR and extracts textual information from the current page based on a descriptive query of what you are looking for.
- submit_for_evaluation: indicate that you believe the task is complete and ready for evaluation. An external reviewer will assess and provide feedback if any aspects of the task remain incomplete.



It is currently {datetime.now().strftime("%Y-%m-%d")}
"""


async def get_action_choice_prompt(
    browser: AgentBrowser, goal: str, feedback: str
) -> str:
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


TASK: Choose the next action that helps you towards the following goal: {goal}

{feedback if feedback else ""}


Rules:
- Always use the extract action if you need to extract specific information from the page (recipe, top comment, title, etc.), even if you can see the information on the page.
- If you need to find a specific element on the page to interact with (e.g. a button, link, etc.), use the scroll_to_content action instead of the scroll action. Only use the scroll action if you need to view more of the page.
- When performing a search via a search bar, use a more general query if the current query is not working.
- For date inputs, type the desired date instead of using the date picker.
- If there is a dropdown menu, select an option before proceeding.

"""


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
    "success": <boolean indicating whether the action was completed successfully>,
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


async def get_next_goal_prompt(browser: AgentBrowser) -> str:
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



TASK: 
1. Describe the current state of the task. Outline what has been done so far and what remains to be done.
2. Determine what the immediate next goal should be. This typically should be a single action to take.

If the task is fully complete, suggest submitting for evaluation.


Output your response in JSON format.
{{
    "task_state": <description of the current state of the task>,
    "next_goal": <the next goal to accomplish>,
}}



Rules:
- Always use the extract action if you need to extract specific information from the page (recipe, top comment, title, etc.), even if you can see the information on the page.
- If you need to find a specific element on the page to interact with (e.g. a button, link, etc.), use the scroll_to_content action instead of the scroll action. Only use the scroll action if you need to view more of the page.
- When performing a search via a search bar, use a more general query if the current query is not working.
- For date inputs, type the desired date instead of using the date picker.
- If there is a dropdown menu, select an option before proceeding.
"""


async def evaluate_goal_completion_prompt(
    browser: AgentBrowser, goal: str, action_result: str
) -> str:
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




TASK: 
1. Evaluate the outcome of the previous action. If a mistake was made, explain why and what needs to be done to correct it.
2. Evaluate if the goal has been completed and provide feedback on the goal's completion. 

Goal: {goal}

{f"Previous action result:\n{action_result}" if action_result else ""}

Use the screenshots to evaluate if the goal has been completed. They capture the state of the page through time in chronological order.

If the goal is not completed, explain why and what needs to be done to complete the goal. If the goal is completed, briefly summarize what was done to complete the goal.


Output your response in JSON format.
{{
    "previous_action_evaluation": <evaluation of the previous action>,
    "completed": <boolean indicating if the goal has been completed>,
    "feedback": <feedback>,
}}
"""


async def get_evaluator_system_prompt() -> str:
    return """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.
-- If you are not sure whether you should believe the content in the response, you should choose unknown.

Provide a verdict on whether the task has been successfully accomplished, either as 'success', 'failed', or 'unknown'. If the task was not accomplished successfully, provide a feedback to the agent on what went wrong or what needs to be done to complete the task.

Output a JSON object with the following format:
{
    "verdict": <success | failed | unknown>
    "feedback": <feedback>
}"""
