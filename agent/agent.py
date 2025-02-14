from openai import AsyncOpenAI
from dotenv import load_dotenv
from agent.browser import AgentBrowser

load_dotenv()

class Agent:
    def __init__(self, identity: str = ""):
        self.client = AsyncOpenAI()
        self.identity = identity
        self.browser = AgentBrowser()

    async def launch(self, url: str = "https://google.com", headless: bool = False):
        await self.browser.launch(url, headless)

    
    async def terminate(self):
        await self.browser.terminate()