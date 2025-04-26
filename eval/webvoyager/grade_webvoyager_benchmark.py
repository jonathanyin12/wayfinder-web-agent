import argparse
import asyncio
import json
import os
from typing import Any, Dict, List, Tuple

from tqdm.asyncio import tqdm_asyncio
from utils.file_io import (
    load_task_definitions,
    load_task_metadata,
    save_task_metadata,
)
from utils.llm_interface import initialize_client
from utils.types import Metadata, TaskData

from eval.webvoyager.grading.aggregation import (
    run_aggregation,  # Assuming run_aggregation is the main entry point
)
from eval.webvoyager.grading.evaluation import (
    evaluate_task_initial,
    evaluate_unclear_task,
)

DEFAULT_TASK_DEFINITIONS = "benchmark/WebVoyager_cleaned_tasks.jsonl"
DEFAULT_CONCURRENCY = 20
DEFAULT_IMG_NUM = 15
DEFAULT_MODEL = "o4-mini"
REEVAL_MODEL = "o4-mini"  # Model specifically for re-evaluation


async def run_initial_evaluations(
    results_dir: str,
    tasks: List[TaskData],
    client: Any,  # Should be AsyncOpenAI or AsyncAzureOpenAI
    model: str,
    max_attached_imgs: int,
    semaphore: asyncio.Semaphore,
) -> List[Tuple[str, Metadata | None]]:
    """Runs initial evaluation for tasks that haven't been evaluated yet.

    Returns:
        A list of tuples: (task_id, metadata or None if errored)
    """
    initial_eval_tasks = []
    tasks_to_run_initial_eval = []
    print("Collecting tasks for initial evaluation...")
    for task_data in tasks:
        task_id = task_data["id"]
        file_dir = os.path.join(results_dir, task_id)
        metadata_path = os.path.join(file_dir, "metadata.json")

        if not os.path.exists(metadata_path):
            print(f"Skipping {file_dir}: metadata file does not exist.")
            continue

        try:
            # Load metadata just to check if auto_eval exists
            with open(metadata_path) as fr:
                metadata_minimal = json.load(fr)

            # Skip if initial evaluation already exists
            if (
                "auto_eval" not in metadata_minimal
                or metadata_minimal["auto_eval"] is None
            ):
                task = asyncio.create_task(
                    evaluate_task_initial(
                        semaphore, file_dir, client, model, max_attached_imgs
                    )
                )
                # Store task_id along with the future
                tasks_to_run_initial_eval.append((task_id, task))
            else:
                print(f"Skipping {task_id}: Already has initial evaluation.")
                # Append result directly if already evaluated
                initial_eval_tasks.append((task_id, load_task_metadata(file_dir)))

        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {metadata_path}. Skipping.")
            initial_eval_tasks.append((task_id, None))  # Mark as error
        except FileNotFoundError:
            # This case should be caught by the os.path.exists check earlier,
            # but included for robustness
            print(f"Warning: Metadata file disappeared for {file_dir}. Skipping.")
            initial_eval_tasks.append((task_id, None))
        except Exception as e:
            print(f"Warning: Error checking task {task_id}: {e}. Skipping.")
            initial_eval_tasks.append((task_id, None))  # Mark as error

    if not tasks_to_run_initial_eval:
        print("No tasks require initial evaluation.")
    else:
        print(
            f"Running initial evaluation for {len(tasks_to_run_initial_eval)} tasks..."
        )
        # Just gather the evaluation tasks
        running_tasks = [t for _, t in tasks_to_run_initial_eval]
        results = await tqdm_asyncio.gather(*running_tasks, desc="Initial Evaluation")

        # Combine results with task IDs
        for i, (task_id, _) in enumerate(tasks_to_run_initial_eval):
            # Results from evaluate_task_initial are (verdict, explanation, cost, metadata)
            _, _, _, metadata_result = results[i]
            initial_eval_tasks.append((task_id, metadata_result))

    return initial_eval_tasks


async def run_reevaluations(
    results_dir: str,
    evaluated_tasks: List[Tuple[str, Metadata | None]],  # Input from initial eval run
    client: Any,
    model: str,
    semaphore: asyncio.Semaphore,
) -> List[Tuple[str, Metadata | None]]:
    """Runs re-evaluation for tasks marked as 'unclear' during initial evaluation.

    Returns:
        A list of tuples: (task_id, updated_metadata or None if errored)
    """
    tasks_to_reevaluate = []
    final_results = []  # To store results for tasks not needing re-eval

    print("Collecting tasks for re-evaluation...")
    for task_id, metadata in evaluated_tasks:
        if metadata is None:
            print(f"Skipping re-eval for {task_id}: Errored during initial check/eval.")
            final_results.append((task_id, None))
            continue

        initial_eval = metadata.get("auto_eval")
        # Check if initial verdict was unclear AND no re-evaluation verdict exists yet
        if (
            initial_eval
            and initial_eval.get("verdict") == "unclear"
            and metadata.get("verdict_after_additional_verification") is None
        ):
            task = asyncio.create_task(
                evaluate_unclear_task(semaphore, task_id, metadata, client, model)
            )
            tasks_to_reevaluate.append((task_id, task))
        else:
            # If not unclear or already re-evaluated, pass through the metadata
            final_results.append((task_id, metadata))

    if not tasks_to_reevaluate:
        print("No tasks require re-evaluation.")
    else:
        print(f"Running re-evaluation for {len(tasks_to_reevaluate)} tasks...")
        running_tasks = [t for _, t in tasks_to_reevaluate]
        reeval_results = await tqdm_asyncio.gather(*running_tasks, desc="Re-evaluation")

        # Combine results with task IDs
        for i, (task_id, _) in enumerate(tasks_to_reevaluate):
            # Results from evaluate_unclear_task are (success_bool, explanation, metadata)
            _, _, metadata_result = reeval_results[i]
            final_results.append((task_id, metadata_result))
            # Save the updated metadata after re-evaluation
            if metadata_result:
                process_dir = os.path.join(results_dir, task_id)
                save_task_metadata(process_dir, metadata_result)

    return final_results


async def main(
    results_dir_name: str,
    model: str,
    max_attached_imgs: int,
    concurrency: int,
    task_definitions_path: str,
):
    client = initialize_client(model)  # Initialize client based on initial eval model
    reeval_client = initialize_client(
        REEVAL_MODEL
    )  # Separate client for re-eval if needed

    tasks = load_task_definitions(task_definitions_path)
    results_abs_path = os.path.abspath(f"runs/{results_dir_name}")
    os.makedirs(results_abs_path, exist_ok=True)

    semaphore = asyncio.Semaphore(concurrency)

    # 1. Run Initial Evaluations
    initially_evaluated_tasks = await run_initial_evaluations(
        results_abs_path,
        tasks,
        client,
        model,
        max_attached_imgs,
        semaphore,
    )

    # 2. Run Re-evaluations for Unclear Tasks
    final_evaluated_tasks = await run_reevaluations(
        results_abs_path,
        initially_evaluated_tasks,
        reeval_client,  # Use potentially different client/model for re-eval
        REEVAL_MODEL,
        semaphore,
    )

    # 3. Aggregate Results
    # The aggregation script reads directly from the saved metadata files,
    # including the updates from initial and re-evaluation steps.
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
        help=f"LLM model for initial evaluation (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max_attached_imgs",
        type=int,
        default=DEFAULT_IMG_NUM,
        help=f"Maximum number of screenshots to attach for initial evaluation (default: {DEFAULT_IMG_NUM})",
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
    # Add argument to potentially skip initial eval or re-eval if needed later

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
