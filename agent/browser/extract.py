import json

import markdownify
from openai import AsyncOpenAI
from playwright.async_api import Page

client = AsyncOpenAI()


async def extract_page_information(page: Page, objective: str):
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
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    response_json = json.loads(response.choices[0].message.content)
    return response_json["information"]
