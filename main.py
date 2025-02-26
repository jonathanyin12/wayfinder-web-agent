import asyncio

from agent import Agent


async def main():
    # agent = Agent(objective="Open the 51st post on hacker news")
    # await agent.launch("https://news.ycombinator.com/news")
    agent = Agent(objective="Add a macbook under $500 to my cart")
    await agent.launch("https://amazon.com")
    await asyncio.sleep(3)
    await agent.terminate()


if __name__ == "__main__":
    asyncio.run(main())
