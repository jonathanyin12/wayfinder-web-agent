"""
Browser action modules for interacting with web pages.
"""

from ..utils import preprocess_page, screenshot
from . import extract, input, interaction, navigation, scroll, search

__all__ = [
    "preprocess_page",
    "search",
    "input",
    "interaction",
    "navigation",
    "screenshot",
    "scroll",
    "extract",
]
