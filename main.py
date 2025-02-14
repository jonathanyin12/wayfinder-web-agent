from agent import Agent
import asyncio





async def main():
    agent = Agent()
    await agent.launch()
    await asyncio.sleep(10)
    await agent.terminate()
        

if __name__ == "__main__":
    asyncio.run(main())

 

