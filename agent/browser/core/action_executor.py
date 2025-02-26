"""
Functions for executing agent actions on the browser.
"""

import logging
from typing import Dict

from playwright.async_api import Page

from ...models import AgentAction
from ..actions.extract import extract_page_information
from ..actions.input import type_text
from ..actions.interaction import click_element
from ..actions.navigation import go_back, go_forward, go_to_url
from ..actions.scroll import scroll_down, scroll_up

# Set up logging
logger = logging.getLogger(__name__)


async def execute_action(
    page: Page, action: AgentAction, label_selectors: Dict[str, str]
) -> None:
    """
    Execute an agent action on the browser.

    Args:
        page: The Playwright page
        action: The agent action to execute
        label_selectors: Dictionary mapping labels to CSS selectors

    Raises:
        RuntimeError: If the browser page is not initialized
        Exception: If there's an error executing the action
    """
    if not page:
        raise RuntimeError("Browser page is not initialized")

    try:
        match action.name:
            case "click_element":
                element_id = action.args["element_id"]
                label_selector = label_selectors[str(element_id)]
                await click_element(page, label_selector)
            case "type_text":
                element_id = action.args["element_id"]
                text = action.args["text"]
                submit = action.args["submit"]
                label_selector = label_selectors[str(element_id)]
                await type_text(page, label_selector, text, submit)
            case "extract_info":
                objective = action.args["objective"]
                return await extract_page_information(page, objective)
            case "scroll":
                direction = action.args["direction"]
                if direction == "down":
                    await scroll_down(page)
                else:
                    await scroll_up(page)
            case "navigate":
                direction = action.args["direction"]
                await go_back(page) if direction == "back" else await go_forward(page)
            case "go_to_url":
                url = action.args["url"]
                await go_to_url(page, url)
            case _:
                logger.warning(f"Unknown action: {action.name}")
    except Exception as e:
        logger.error(f"Error executing action {action.name}: {e}")
        raise


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click on an element on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "number",
                        "description": "The id of the element to click on.",
                    },
                },
                "required": ["element_id"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into an element on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "number",
                        "description": "The id of the element to type text into.",
                    },
                    "text": {
                        "type": "string",
                        "description": "The text to type into the element.",
                    },
                    "submit": {
                        "type": "boolean",
                        "description": "Whether to submit the text after typing it.",
                    },
                },
                "required": ["element_id", "text", "submit"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "The direction to scroll ('up' or 'down').",
                    },
                },
                "required": ["direction"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_info",
            "description": "Extract information from the page relevant to the objective.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {
                        "type": "string",
                        "description": "The objective or goal for information extraction.",
                    }
                },
                "required": ["objective"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate browser history forward or back.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["forward", "back"],
                        "description": "The direction to navigate ('forward' or 'back').",
                    }
                },
                "required": ["direction"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "go_to_url",
            "description": "Navigate directly to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to.",
                    }
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end",
            "description": "End the current task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "The reason for ending the task.",
                    },
                    "output": {
                        "type": "string",
                        "description": "The output of the task if the task is an extraction/retrieval task.",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
            "strict": False,
        },
    },
]
