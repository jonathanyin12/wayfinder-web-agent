import markdownify
from playwright.async_api import Page

from web_agent.browser.core.page import browser_action
from web_agent.llm import LLMClient


@browser_action
async def extract(page: Page, llm_client: LLMClient, information_to_extract: str):
    page_content = await page.content()
    markdown_content = markdownify.markdownify(page_content)

    prompt = f"""You are a specialized text extraction assistant. Your task is to find and extract information pertaining to the following query: {information_to_extract}.

If there is no information on the page pertaining to the query, say so. Do not try to answer the query based on information not in the page content.

Here is the page content in markdown format:
{markdown_content}
"""
    response = await llm_client.make_call(
        [{"role": "user", "content": prompt}],
        "gpt-4.1",
        json_format=False,
    )
    return response.content
