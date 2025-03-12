"""
Browser action modules for interacting with web pages.
"""

from ..utils import annotation, screenshot
from . import input, interaction, navigation, scroll, search

__all__ = [
    "annotation",
    "search",
    "input",
    "interaction",
    "navigation",
    "screenshot",
    "scroll",
]
