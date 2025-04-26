import argparse
import asyncio
import json
import logging
import os
import random
import shutil
import sys
from datetime import datetime
from typing import List

sys.path.append("..")
sys.path.append("../..")
sys.path.append("../../..")
from utils import TaskData

from web_agent.web_agent import WebAgent


async def run_task_with_semaphore(
    task: TaskData,
    semaphore: asyncio.Semaphore,
    output_dir: str,
) -> None:
    async with semaphore:
        # Add random delay before starting the task so that the tasks are staggered
        await asyncio.sleep(random.uniform(0, 10))
        print(f"Running task {task['id']}")
        agent = WebAgent(
            objective=task["ques"],
            initial_url=task["web"],
            output_dir=f"{output_dir}/{task['id']}",
            headless=True,
        )
        await agent.run()


async def main(max_concurrent_tasks: int, output_dir: str) -> None:
    semaphore = asyncio.Semaphore(max_concurrent_tasks)

    output_dir = f"runs/{output_dir}"
    all_tasks: List[TaskData] = []
    with open("benchmark/WebVoyager_cleaned_tasks.jsonl", "r") as f:
        for line in f:
            all_tasks.append(json.loads(line))

    random.seed(42)
    random.shuffle(all_tasks)
    all_tasks = all_tasks[:100]

    # Skip tasks that have already been run
    tasks = []
    for task in all_tasks:
        task_id = task["id"]
        if os.path.exists(f"{output_dir}/{task_id}"):
            if os.path.exists(f"{output_dir}/{task_id}/metadata.json"):
                print(f"Task {task_id} already completed, skipping")
                continue
            else:
                print(
                    f"Task {task_id} is missing metadata.json, deleting task directory and running again"
                )
                shutil.rmtree(f"{output_dir}/{task_id}")  # delete the task directory
                tasks.append(task)
        else:
            tasks.append(task)
    print(f"Running {len(tasks)} tasks")

    asyncio_tasks = []
    for task in tasks:
        asyncio_tasks.append(
            asyncio.create_task(run_task_with_semaphore(task, semaphore, output_dir))
        )
    await asyncio.gather(*asyncio_tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Run browser tasks with concurrent execution"
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            help="Output directory",
        )
        parser.add_argument(
            "--max-concurrent",
            type=int,
            default=10,
            help="Maximum number of concurrent tasks",
        )
        args = parser.parse_args()

        logging.info(f"Running with {args.max_concurrent} concurrent tasks")

        asyncio.run(main(args.max_concurrent, args.output_dir))
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.exception("Fatal error occurred")
