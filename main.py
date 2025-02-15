import asyncio

from agent import Agent


async def main():
    agent = Agent(objective="buy a macbook")
    await agent.launch("https://amazon.com")
    await asyncio.sleep(3)
    await agent.terminate()


if __name__ == "__main__":
    asyncio.run(main())
