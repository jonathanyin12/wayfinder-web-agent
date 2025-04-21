import argparse
import asyncio
import json
import logging
import os
import random
import shutil
import sys
from datetime import datetime
from typing import List, TypedDict

sys.path.append(".")
from agent.web_agent import WebAgent


class TaskData(TypedDict):
    id: str
    web: str
    web_name: str
    ques: str


async def run_task(task: TaskData, output_dir: str) -> None:
    # check if the task has already been run
    if os.path.exists(f"{output_dir}/{task['id']}"):
        if os.path.exists(f"{output_dir}/{task['id']}/metadata.json"):
            print(f"Task {task['id']} already exists, skipping")
            return
        else:
            print(
                f"Task {task['id']} already exists, but metadata.json does not exist, running again"
            )
            shutil.rmtree(f"{output_dir}/{task['id']}")
    else:
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

    tasks: List[TaskData] = []
    with open("eval/WebVoyager_data.jsonl", "r") as f:
        for line in f:
            tasks.append(json.loads(line))

    # remove impossible tasks
    with open("eval/WebVoyagerImpossibleTasks.json", "r") as f:
        impossible_tasks_json = json.load(f)
        impossible_tasks = set()
        for web_name in impossible_tasks_json:
            for task_id in impossible_tasks_json[web_name]:
                impossible_tasks.add(task_id)

    tasks = [task for task in tasks if task["id"] not in impossible_tasks]

    # randomize the order of tasks
    random.seed(42)
    random.shuffle(tasks)
    tasks = tasks[:50]
    print(f"Running {len(tasks)} tasks")

    async def run_task_with_semaphore(
        task: TaskData,
        semaphore: asyncio.Semaphore,
        output_dir: str,
    ) -> None:
        async with semaphore:
            # Add random delay before starting the task so that the tasks are staggered
            await asyncio.sleep(random.uniform(0, 10))
            await run_task(task, output_dir)

    all_tasks = []
    for task in tasks:
        all_tasks.append(
            asyncio.create_task(run_task_with_semaphore(task, semaphore, output_dir))
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
            default=10,
            help="Maximum number of concurrent tasks",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default=f"eval/webvoyager/{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            help="Output directory (default: eval/webvoyager)",
        )
        args = parser.parse_args()

        logging.info(f"Running with {args.max_concurrent} concurrent tasks")

        asyncio.run(main(args.max_concurrent, args.output_dir))
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.exception("Fatal error occurred")
