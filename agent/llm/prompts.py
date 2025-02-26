from typing import Any, Dict


class PromptManager:
    def __init__(self, objective: str):
        self.objective = objective

    def get_system_prompt(self) -> str:
        """Returns the system prompt for the agent"""
        return f"""You are a helpful web browsing assistant.    
        
Here is your ultimate objective: {self.objective}.

POSSIBLE ACTIONS:
- click_element: click a specific element on the page
- type_text: type text into a text box on the page
- extract_info: extract specific information from the page. 
- scroll: scroll up or down on the page
- navigate: go back to the previous page or go forward to the next page
- go_to_url: go to a specific url
- end: declare that you have completed the task


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

Here are the elements you can interact with (element_id: element_html):
{interactable_elements}


TASK:
1. Provide a detailed summary of key information relevant to the task from the current page which is not yet in the task history memory.

2. Reason about whether the previous action ("{last_action_description}") was successful or not. Carefully compare the before and after screenshots to verify whether the action was successful. Consider what UX changes are expected for the action you took.

3. Summarize what has been accomplished since the beginning. Also, broadly describe what else is remaining of the overall objective.

4. Reason about what is an appropriate next step given the current state of the page and the overall objective. 
- If you are stuck, try alternative approaches. DO NOT REPEATEDLY TRY THE SAME ACTION IF IT IS NOT WORKING. 
- This must be achievable in a single action, so avoid something that require multiple actions like first scrolling then clicking.
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

The exact url is {url}.

The first screenshot is the current state of the page after the last action was performed.

The second screenshot is the current page annotated with bounding boxes drawn around elements you can interact with. At the top left of the bounding box is a number that corresponds to the id of the element. Each id is associated with the simplified html of the element.


Here are the elements you can interact with (element_id: element_html):
{interactable_elements}


TASK: 
Choose the action that best matches the following next step:
{next_step}
"""
