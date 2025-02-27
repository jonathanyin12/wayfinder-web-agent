from typing import Any, Dict

from agent.models import AgentAction


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
- end: declare that you have completed the task
"""

    async def get_planning_prompt(
        self,
        site_name: str,
        page_position: str,
        url: str,
        interactable_elements: str,
        last_action: AgentAction | None = None,
    ) -> str:
        """Returns the prompt template for planning the next action"""
        if not last_action:
            return f"""CONTEXT:
You are on a page of {site_name}. {page_position}

The exact url is {url[:50] + "..." if len(url) > 50 else url}.

The screenshot is the current state of the page.


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
You are on a page of {site_name}. {page_position}

The exact url is {url[:50] + "..." if len(url) > 50 else url}.

The last action you performed was: {last_action.description}

The first screenshot is the state of the page before the last action was performed.

The second screenshot is the current state of the page, after the last action was performed.


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
        site_name: str,
        page_position: str,
        url: str,
        interactable_elements: str,
        next_step: Dict[str, Any],
    ) -> str:
        """Returns the prompt template for planning the next action"""
        return f"""CONTEXT:
You are on a page of {site_name}. {page_position}

The exact url is {url[:50] + "..." if len(url) > 50 else url}.

The first screenshot is the current state of the page after the last action was performed.

The second screenshot is the current page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the id of the element. Each id is associated with the simplified html of the element.


Here are the elements you can interact with (element_id: element_html):
{interactable_elements}


TASK: 
Choose the action that best matches the following next step:
{next_step}

The entire next step may not be achievable through a single action and may require multiple actions (e.g. scroll down first, then click on an element). If so, simply output the first action. If no currently visible elements are relevant to the next step, scrolling may be required to reveal the relevant elements.
"""
