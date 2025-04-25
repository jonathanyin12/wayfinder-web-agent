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
            "description": "Click on a text box and type text into it. This will automatically clear the text box before typing.",
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
                },
                "required": ["element_id", "text"],
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
    {
        "type": "function",
        "function": {
            "name": "find",
            "description": "Search the page for specific content and automatically scrolls to its location if found. Provide as much context/detail as possible about what you are looking for.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content_to_find": {
                        "type": "string",
                        "description": "The content to find on the page. Provide as much context as possible.",
                    }
                },
                "required": ["content_to_find"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract",
            "description": "Gets the entire text content of the page and extracts textual information based on a descriptive query. The content does not need to be currently visible on the page to be extracted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "information_to_extract": {
                        "type": "string",
                        "description": "A detailed natural language description of the specific text you want to find and extract. For example: 'the headline of the news article', 'the total price in the shopping cart', 'the first paragraph of the blog post'.",
                    }
                },
                "required": ["information_to_extract"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
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
    {
        "type": "function",
        "function": {
            "name": "submit_for_evaluation",
            "description": "Indicate that you believe the task is complete and ready for evaluation. An external reviewer will assess and provide feedback if any aspects of the task remain incomplete.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]
