"""
Extract actions for retrieving information from web pages.
"""

import json

import markdownify
from playwright.async_api import Page

from agent.llm.client import LLMClient

client = LLMClient()


async def extract_page_information(page: Page, objective: str) -> str:
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
    
Respond in JSON format as follows:
{{
    "information": "Information relevant to the objective"
}}

Here is the page content in markdown format:
{markdown_content}
"""
    response = await client.make_call(
        [{"role": "user", "content": prompt}],
        "gpt-4o",
    )
    response_json = json.loads(response.choices[0].message.content)
    return response_json["information"]
