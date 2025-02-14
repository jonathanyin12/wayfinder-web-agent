from openai import AsyncOpenAI
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

class Agent:
    def __init__(self, identity: str = ""):
        self.client = AsyncOpenAI()
        self.identity = identity

    async def launch(self, url: str = "https://google.com"):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False, args=['--start-maximized'])
        context = await self.browser.new_context(no_viewport=True)
        page = await context.new_page()
        await page.goto(url)


    async def terminate(self):
        await self.browser.close()
        await self.playwright.stop()