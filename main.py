import asyncio

from agent import Agent


async def main():
    agent = Agent()
    await agent.launch("https://amazon.com")
    await asyncio.sleep(10)
    await agent.terminate()


if __name__ == "__main__":
    asyncio.run(main())
