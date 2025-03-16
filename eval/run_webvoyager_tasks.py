import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import datetime
from typing import List, TypedDict

sys.path.append(".")
from agent.web_agent import WebAgent


class TaskData(TypedDict):
    id: str
    web: str
    ques: str


async def run_task(task: TaskData, model_provider: str, output_dir: str) -> None:
    print(f"Running task {task['id']}")
    agent = WebAgent(
        objective=task["ques"],
        initial_url=task["web"],
        output_dir=f"{output_dir}/{task['id']}",
        headless=True,
    )
    await agent.run()


async def main(max_concurrent_tasks: int, model_provider: str, output_dir: str) -> None:
    semaphore = asyncio.Semaphore(max_concurrent_tasks)

    tasks: List[TaskData] = []
    with open("eval/WebVoyager_data.jsonl", "r") as f:
        for line in f:
            tasks.append(json.loads(line))

    # remove impossible tasks
    with open("eval/WebVoyagerImpossibleTasks.json", "r") as f:
        impossible_tasks = set(json.load(f))
    tasks = [task for task in tasks if task["id"] not in impossible_tasks]

    # randomize the order of tasks
    # random.seed(42)
    # random.shuffle(tasks)
    print(f"Running {len(tasks)} tasks")

    tasks = tasks[:5]

    async def run_task_with_semaphore(
        task: TaskData,
        model_provider: str,
        semaphore: asyncio.Semaphore,
        output_dir: str,
    ) -> None:
        async with semaphore:
            await run_task(task, model_provider, output_dir)

    all_tasks = []
    for task in tasks:
        all_tasks.append(
            asyncio.create_task(
                run_task_with_semaphore(task, model_provider, semaphore, output_dir)
            )
        )

    await asyncio.gather(*all_tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Run browser tasks with concurrent execution"
        )
        parser.add_argument(
            "--max-concurrent",
            type=int,
            default=3,
            help="Maximum number of concurrent tasks (default: 3)",
        )
        parser.add_argument(
            "--model-provider",
            type=str,
            default="azure",
            help="Model provider (default: azure)",
            choices=[
                "azure",
            ],
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default=f"eval/webvoyager/{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            help="Output directory (default: eval/webvoyager)",
        )
        args = parser.parse_args()

        logging.info(f"Running with {args.max_concurrent} concurrent tasks")

        asyncio.run(main(args.max_concurrent, args.model_provider, args.output_dir))
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.exception("Fatal error occurred")
