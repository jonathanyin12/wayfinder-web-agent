import asyncio

from agent import ReActAgent


async def main():
    agent = ReActAgent(
        objective="Add a macbook to my cart",
        initial_url="https://www.apple.com/shop/buy-mac/macbook-air",
    )
    # agent = Agent(
    #     objective="Find a recipe for a vegetarian lasagna that has at least a four-star rating and uses zucchini.",
    #     initial_url="https://www.allrecipes.com/",
    # )

    # agent = Agent(objective="Find the top comment on the 51st post on hacker news")
    # agent = Agent(
    #     objective="Go to Reddit, search for 'browser-use', click on the first post and return the first comment."
    # )
    await agent.execute()


if __name__ == "__main__":
    asyncio.run(main())
