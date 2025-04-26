import argparse
import asyncio
import json
import os
from typing import Any, List

from grading.aggregation import (
    run_aggregation,  # Assuming run_aggregation is the main entry point
)
from grading.evaluation import evaluate_task
from tqdm.asyncio import tqdm_asyncio
from utils.file_io import load_task_definitions, load_task_metadata
from utils.llm_interface import initialize_client
from utils.types import TaskData

DEFAULT_TASK_DEFINITIONS = "benchmark/WebVoyager_cleaned_tasks.jsonl"
DEFAULT_CONCURRENCY = 20
DEFAULT_IMG_NUM = 15
DEFAULT_MODEL = "o4-mini"


async def run_evaluations(
    results_dir: str,
    tasks: List[TaskData],
    client: Any,
    model: str,
    max_attached_imgs: int,
    concurrency: int,
) -> None:
    """Runs evaluation for tasks that haven't been evaluated yet.

    Calls evaluate_task which handles potential re-evaluation internally.

    Returns:
        A list of tuples: (task_id, metadata or None if errored)
    """
    semaphore = asyncio.Semaphore(concurrency)

    tasks_to_run_eval = []
    print("Collecting tasks for evaluation...")
    for task_data in tasks:
        task_id = task_data["id"]
        file_dir = os.path.join(results_dir, task_id)
        metadata_path = os.path.join(file_dir, "metadata.json")

        if not os.path.exists(metadata_path):
            print(f"Skipping {file_dir}: metadata file does not exist.")
            continue

        try:
            # Load metadata just to check if evaluation_result exists
            metadata = load_task_metadata(file_dir)

            # Check if evaluation_result field already exists and is not None
            if metadata.get("evaluation_result") is not None:
                print(f"Skipping {task_id}: Already has evaluation result.")
                # Append result directly if already evaluated (load full metadata)
            else:
                # Needs evaluation
                task = asyncio.create_task(
                    evaluate_task(semaphore, file_dir, client, model, max_attached_imgs)
                )
                # Store task_id along with the future
                tasks_to_run_eval.append(task)

        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {metadata_path}. Skipping.")
        except FileNotFoundError:
            print(f"Warning: Metadata file disappeared for {file_dir}. Skipping.")
        except Exception as e:
            print(f"Warning: Error checking task {task_id}: {e}. Skipping.")

    if not tasks_to_run_eval:
        print("No tasks require evaluation.")
    else:
        print(f"Running evaluation for {len(tasks_to_run_eval)} tasks...")
        await tqdm_asyncio.gather(*tasks_to_run_eval, desc="Evaluation")


async def main(
    results_dir_name: str,
    model: str,
    max_attached_imgs: int,
    concurrency: int,
    task_definitions_path: str,
):
    client = initialize_client(model)  # Initialize client based on evaluation model
    # reeval_client removed

    tasks = load_task_definitions(task_definitions_path)
    results_abs_path = os.path.abspath(f"runs/{results_dir_name}")
    os.makedirs(results_abs_path, exist_ok=True)

    # 1. Run Evaluations (handles initial + re-evaluation)
    await run_evaluations(
        results_abs_path,
        tasks,
        client,
        model,
        max_attached_imgs,
        concurrency,
    )

    # 2. Aggregate Results (reads final state from metadata)
    print("\nStarting final aggregation...")
    run_aggregation(results_dir_name, task_definitions_path)
    print("\nGrading complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grade WebVoyager benchmark results.")
    parser.add_argument(
        "results_dir",
        type=str,
        help="Directory name within 'runs/' containing the execution results.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        type=str,
        help=f"LLM model for evaluation (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max_attached_imgs",
        type=int,
        default=DEFAULT_IMG_NUM,
        help=f"Maximum number of screenshots to attach for evaluation (default: {DEFAULT_IMG_NUM})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Maximum number of concurrent API calls (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--task_definitions",
        type=str,
        default=DEFAULT_TASK_DEFINITIONS,
        help=f"Path to the JSONL file with task definitions (default: {DEFAULT_TASK_DEFINITIONS})",
    )

    args = parser.parse_args()

    asyncio.run(
        main(
            args.results_dir,
            args.model,
            args.max_attached_imgs,
            args.concurrency,
            args.task_definitions,
        )
    )
