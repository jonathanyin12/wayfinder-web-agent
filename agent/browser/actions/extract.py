"""
Extract actions for retrieving information from web pages.
"""

import markdownify
from playwright.async_api import Page

from agent.browser.core.page import browser_action
from agent.llm.client import LLMClient

client = LLMClient()


@browser_action
async def extract_info(page: Page, objective: str) -> str:
    """
    Extract information from the page relevant to the given objective.

    Uses GPT-4o to analyze the page content and extract relevant information
    based on the specified objective.

    Args:
        page: The Playwright page
        objective: The objective or goal for information extraction

    Returns:
        A string containing the extracted information
    """
    page_content = await page.content()
    markdown_content = markdownify.markdownify(page_content)

    prompt = f"""Your high level task is to retrieve all information from the page that is relevant to the objective. Your objective is the following: {objective}. 
    

Here is the page content in markdown format:
{markdown_content}


Output your response in markdown format if there is relevant information to the objective. If there is no relevant information, just say "No relevant information found".
"""
    response = await client.make_call(
        [{"role": "user", "content": prompt}],
        "gpt-4o",
        json_format=False,
    )
    if not response.content:
        raise ValueError("No response content")
    return response.content
