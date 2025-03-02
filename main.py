import asyncio

from agent import Agent


async def main():
    agent = Agent(objective="Add a macbook to my cart")
    await agent.execute("https://amazon.com")
    # agent = Agent(objective="Buy a macbook from bestbuy")
    # await agent.execute()

    # agent = Agent(objective="Find the top comment on the 51st post on hacker news")
    # agent = Agent(
    #     objective="Go to Reddit, search for 'browser-use', click on the first post and return the first comment."
    # )
    # await agent.launch()


if __name__ == "__main__":
    asyncio.run(main())
