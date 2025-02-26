"""
URL utility functions for browser operations.
"""

from urllib.parse import urlparse


def get_base_url(url: str) -> str:
    """
    Extract the base domain from a URL.

    Args:
        url: The full URL to parse

    Returns:
        The base domain (netloc) from the URL
    """
    parsed_url = urlparse(url)
    base_url = parsed_url.netloc
    return base_url
