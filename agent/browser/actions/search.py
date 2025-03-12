import markdownify
from playwright.async_api import Page

from agent.browser.core.page import browser_action
from agent.llm.client import LLMClient

client = LLMClient()


@browser_action
async def search_page(page: Page, query: str) -> str:
    """
    Search the entire page for the given query.

    Uses GPT-4o to analyze the page content and search for the given query.

    Args:
        page: The Playwright page
        query: The query to search for

    Returns:
        A string containing the relevant information
    """
    page_content = await page.content()
    markdown_content = markdownify.markdownify(page_content)

    prompt = f"""Your high level task is to return information from the page that is relevant to the following query: {query}. 
    

Here is the page content in markdown format:
{markdown_content}


Output your response in markdown format. If there is no relevant information, just say "No relevant information found".
"""
    response = await client.make_call(
        [{"role": "user", "content": prompt}],
        "gpt-4o",
        json_format=False,
    )
    if not response.content:
        raise ValueError("No response content")
    return response.content
