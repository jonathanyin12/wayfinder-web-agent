import os
from pathlib import Path

# Path to the JavaScript files
JS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))


def load_js_file(filename: str) -> str:
    """
    Load a JavaScript file and return its contents as a string.

    Args:
        filename: The name of the JavaScript file to load

    Returns:
        The contents of the JavaScript file
    """
    js_file_path = JS_DIR / filename
    with open(js_file_path, "r") as file:
        return file.read()
