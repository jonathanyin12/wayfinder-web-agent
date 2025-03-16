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
                    "amount": {
                        "type": "number",
                        "description": "The fraction of the page height to scroll. 0.75 is a reasonable default. Use 0.4 to scroll a little and > 0.9 to scroll a lot.",
                    },
                },
                "required": ["direction", "amount"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "search_page",
    #         "description": "Search the entire page for information relevant to the query.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {
    #                     "type": "string",
    #                     "description": "The information to search for. This should be as detailed and specific as possible.",
    #                 }
    #             },
    #             "required": ["query"],
    #             "additionalProperties": False,
    #         },
    #         "strict": True,
    #     },
    # },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Go back to the previous page or go forward to the next page",
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
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "ask_user",
    #         "description": "Ask the user a question.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "question": {
    #                     "type": "string",
    #                     "description": "The question to ask the user. Be very detailed on why you need help and what your question is.",
    #                 }
    #             },
    #             "required": ["question"],
    #             "additionalProperties": False,
    #         },
    #         "strict": True,
    #     },
    # },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Declare that you have completed the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "The reason why you believe you have completed the task.",
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
