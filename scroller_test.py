import asyncio
from datetime import datetime

from agent.agents.scroller.scroller import ScrollAgent
from agent.browser.core.browser import AgentBrowser


async def main():
    # initial_url = "https://arxiv.org/search/?query=On+the+Sentence+Embeddings+from+Pre-trained+Language+Models&searchtype=all&source=header"
    # content_to_find = "Paper by Chaofan Li"
    initial_url = "https://www.apple.com/shop/buy-mac/macbook-air"
    content_to_find = "Select button"
    browser = AgentBrowser(
        initial_url=initial_url,
        output_dir=f"test/{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        headless=False,
    )

    await browser.launch()
    page = browser.current_page.page

    scroller = ScrollAgent(
        content_to_find=content_to_find,
        page=page,
        full_page_screenshot=browser.current_page.full_page_screenshot,
    )
    result = await scroller.run()
    print(result)
    await asyncio.sleep(10)

    await browser.terminate()


if __name__ == "__main__":
    asyncio.run(main())
