import asyncio

from agent import Agent


async def main():
    # agent = Agent(
    #     objective="Add a macbook to my cart",
    #     initial_url="https://www.apple.com/shop/buy-mac/macbook-air",
    # )
    # agent = Agent(objective="Buy a macbook from bestbuy")
    # await agent.execute()

    agent = Agent(
        objective="Find the top comment on the 51st post on hacker news",
        initial_url="https://news.ycombinator.com/",
    )
    # agent = Agent(
    #     objective="Go to Reddit, search for 'browser-use', click on the first post and return the first comment."
    # )
    # await agent.launch()
    await agent.execute()


if __name__ == "__main__":
    asyncio.run(main())
