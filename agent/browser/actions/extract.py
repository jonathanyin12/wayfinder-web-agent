import markdownify
from playwright.async_api import Page

from agent.browser.core.page import browser_action
from agent.llm import LLMClient

llm_client = LLMClient()


@browser_action
async def extract(page: Page, information_to_extract: str):
    page_content = await page.content()
    markdown_content = markdownify.markdownify(page_content)

    prompt = f"""You are a specialized text extraction assistant. Your task is to find and extract information pertaining to the following query: {information_to_extract}.

Here is the page content in markdown format:
{markdown_content}
"""
    response = await llm_client.make_call(
        [{"role": "user", "content": prompt}],
        "gpt-4.1",
        json_format=False,
    )
    return response.content
