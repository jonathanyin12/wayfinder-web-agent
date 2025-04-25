import asyncio

from web_agent import WebAgent


async def main():
    agent = WebAgent(
        objective="Add a Starlight 13-in MacBook Air to my cart.",
        initial_url="https://www.apple.com/shop/buy-mac/macbook-air",
    )

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
