import asyncio
from datetime import datetime

from agent.browser.actions.scroll import scroll_to_content
from agent.browser.core.browser import AgentBrowser

tests = {
    # "arxiv": {
    #     "initial_url": "https://arxiv.org/search/?query=On+the+Sentence+Embeddings+from+Pre-trained+Language+Models&searchtype=all&source=header",
    #     "content_to_find": "Paper by Chaofan Li",
    # },
    # "amazon": {
    #     "initial_url": "https://www.amazon.com/Ozlo-Sleepbuds%C2%AE-Comfortable-Headphones-Science-Backed/dp/B0DJB1ZL8V/142-0259511-3271846?content-id=amzn1.sym.67f8cf21-ade4-4299-b433-69e404eeecf1&pd_rd_i=B0DJB1ZL8V&pd_rd_r=d57ed809-f8a6-498d-8ffc-24e029bb1bb8&pd_rd_w=W5K4T&pd_rd_wg=PPfYJ&pf_rd_p=67f8cf21-ade4-4299-b433-69e404eeecf1&pf_rd_r=J95GF0WAPGRCX0W82X0K&psc=1",
    #     "content_to_find": "Review section",
    # },
    # "apple": {
    #     "initial_url": "https://www.apple.com/shop/buy-mac/macbook-air",
    #     "content_to_find": "Select button",
    # },
    # "apple_2": {
    #     "initial_url": "https://www.apple.com/shop/buy-mac/macbook-air",
    #     "content_to_find": "Add to cart button",
    # },
    # "allrecipes": {
    #     "initial_url": "https://www.allrecipes.com/recipe/229764/easy-vegetarian-spinach-lasagna/",
    #     "content_to_find": "Serving size",
    # },
    "allrecipes_2": {
        "initial_url": "https://www.allrecipes.com/recipe/24085/spicy-vegetarian-lasagna/",
        "content_to_find": "Nutrition Facts",
    },
    # "pillow": {
    #     "initial_url": "https://pillow.readthedocs.io/en/stable/reference/ImageFont.html",
    #     "content_to_find": "FreeTypeFont class",
    # },
}


async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for test_name, test_data in tests.items():
        test_dir = f"scrolling_tests/{timestamp}/{test_name}"
        browser = AgentBrowser(
            initial_url=test_data["initial_url"],
            output_dir=test_dir,
            headless=False,
        )

        await browser.launch()
        page = browser.current_page.page
        result = await scroll_to_content(
            page=page,
            content_to_find=test_data["content_to_find"],
            full_page_screenshot=browser.current_page.full_page_screenshot,
        )
        print(result)

        screenshot = await page.screenshot(full_page=False)
        with open(
            f"{test_dir}/final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "wb",
        ) as f:
            f.write(screenshot)

        await browser.terminate()


if __name__ == "__main__":
    asyncio.run(main())
