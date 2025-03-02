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
                        "description": "Whether to submit the text after typing it. Set to true when the input field requires form submission (like search boxes or login forms). Set to false when you want to type without submitting (like filling out multiple fields before submission).",
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
            "description": "Extract textual information from the entire page relevant to the objective.",
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
            "name": "switch_tab",
            "description": "Switch to a different browser tab by index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_index": {
                        "type": "number",
                        "description": "The index of the tab to switch to (0-based).",
                    }
                },
                "required": ["tab_index"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end",
            "description": "Declare that you have completed the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "The reason for ending the task.",
                    },
                    "final_response": {
                        "type": "string",
                        "description": "The final response/answer to the task. Include detailed information if the task involved gathering specific information (e.g. a recipe, a product description, summary of a page, etc.).",
                    },
                },
                "required": ["reason", "final_response"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]
