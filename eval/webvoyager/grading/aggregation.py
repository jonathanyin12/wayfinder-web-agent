import json
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.file_io import load_task_dict, save_tasks_to_jsonl
from utils.types import EvaluationResult, Metadata, TaskData


@dataclass
class ProcessedTaskInfo:
    """Holds the results of processing a single task's metadata."""

    status: str  # 'ok', 'error_file_not_found', 'error_json', 'error_processing'
    final_verdict: str | None = "error"  # Default to error, updated upon success
    initial_verdict: str | None = None
    iterations: int | None = None
    run_cost: float = 0.0
    total_eval_cost: float = 0.0
    metadata_exists: bool = (
        False  # Helps differentiate file missing vs processing error
    )


def _process_single_task(task_id: str, results_dir: str) -> ProcessedTaskInfo:
    """Processes metadata for a single task, handling file I/O and parsing."""
    metadata_path = os.path.join(results_dir, task_id, "metadata.json")
    result = ProcessedTaskInfo(
        status="error_file_not_found"
    )  # Start with file not found

    if not os.path.exists(metadata_path):
        print(f"Warning: Metadata file not found for task {task_id}. Marking as error.")
        # status already set, metadata_exists is False by default
        return result

    # File exists, update status possibility and flag
    result.metadata_exists = True
    result.status = "error_json"  # Assume JSON error next

    try:
        with open(metadata_path) as fr:
            # Assuming Metadata is compatible with Dict[str, Any] for loading
            metadata: Metadata = json.load(fr)

        result.status = "error_processing"  # Assume processing error next

        # --- Extract Data ---
        result.run_cost = metadata.get("run_cost", 0.0)
        result.iterations = metadata.get("iterations")  # Can be None

        # Assuming EvaluationResult is compatible with Dict[str, Any]
        evaluation_result: Optional[EvaluationResult] = metadata.get(
            "evaluation_result"
        )

        current_total_eval_cost = 0.0
        if evaluation_result:
            initial_eval = evaluation_result.get("evaluation")
            re_eval = evaluation_result.get("re_evaluation")
            if initial_eval:
                # Assuming Evaluation is compatible with Dict[str, Any]
                current_total_eval_cost += initial_eval.get("eval_cost", 0.0)
            if re_eval:
                # Assuming Evaluation is compatible with Dict[str, Any]
                current_total_eval_cost += re_eval.get("eval_cost", 0.0)

            # Determine final verdict
            result.final_verdict = evaluation_result.get("final_verdict", "error")
            result.initial_verdict = evaluation_result.get("initial_verdict", "error")
        else:
            # No evaluation result found, keep default 'error' verdict
            print(f"Warning: No evaluation_result found for {task_id}.")
            result.final_verdict = "error"  # Explicitly set, though default
            result.initial_verdict = (
                "error"  # Also set initial to error if no eval result
            )

        # Assign the calculated total eval cost
        result.total_eval_cost = current_total_eval_cost

        # If we got here, processing was successful
        result.status = "ok"

    except json.JSONDecodeError:
        print(f"Warning: Could not decode JSON from {metadata_path}. Marking as error.")
        # Status is already 'error_json', final_verdict remains 'error'
    except Exception as e:
        print(f"Warning: Error processing {metadata_path}: {e}. Marking as error.")
        result.status = "error_processing"  # Update status
        # final_verdict remains 'error'

    return result


def _calculate_stats(
    data: Sequence[float | int],
) -> Tuple[Optional[float], Optional[float]]:
    """Calculates mean and standard deviation for a sequence of numbers."""
    if not data:
        return None, None
    mean = statistics.mean(data)
    std_dev = statistics.stdev(data) if len(data) > 1 else 0.0
    return mean, std_dev


def _calculate_web_stats(
    web_name: str,
    task_ids: List[str],  # Pass task IDs associated with this website
    iterations: List[int],
    run_costs: List[float],
    total_eval_costs: List[float],
    successful_count: int,
    processed_count: int,
    all_error_ids: List[str],  # Needed to count errors specific to this web
) -> Dict[str, Any]:
    """Calculates and formats statistics for a single website."""
    stats: Dict[str, Any] = {}

    stats["total_tasks_processed"] = processed_count
    stats["final_successful_tasks"] = successful_count
    stats["task_ids"] = task_ids  # Keep track of which tasks belong to this web

    avg_iterations, std_dev_iterations = _calculate_stats(iterations)
    stats["avg_iterations"] = avg_iterations
    stats["std_dev_iterations"] = std_dev_iterations

    # Use None for avg cost if list is empty
    stats["avg_run_cost"], _ = _calculate_stats(run_costs)
    stats["avg_total_eval_cost"], _ = _calculate_stats(total_eval_costs)

    success_rate = (
        (successful_count / processed_count * 100) if processed_count > 0 else 0.0
    )
    stats["success_rate"] = success_rate

    # Count errors specific to this website
    web_error_count = sum(1 for tid in task_ids if tid in all_error_ids)
    stats["error_count"] = web_error_count

    # --- Print Stats --- (Moved printing inside helper for encapsulation)
    if processed_count > 0:
        print(
            f"{web_name} Final Success Rate: {success_rate:.2f}% ({successful_count}/{processed_count} tasks)"
        )
        stat_line_parts = []
        if avg_iterations is not None and std_dev_iterations is not None:
            stat_line_parts.append(
                f"Avg Iter: {avg_iterations:.2f} (± {std_dev_iterations:.2f})"
            )
        # Check for None before formatting cost strings
        if stats["avg_run_cost"] is not None:
            stat_line_parts.append(f"Avg Run Cost: ${stats['avg_run_cost']:.4f}")
        if stats["avg_total_eval_cost"] is not None:
            stat_line_parts.append(
                f"Avg Total Eval Cost: ${stats['avg_total_eval_cost']:.4f}"
            )

        stat_line_parts.append(f"Errors: {web_error_count}")
        print(f"  [{', '.join(stat_line_parts)}]")
    else:
        print(f"{web_name}: No tasks processed.")

    return stats


def analyze_results(
    task_dict: Dict[str, TaskData],
    results_dir: str,
) -> Tuple[
    Dict[str, Dict[str, Any]],
    List[str],
    List[str],
    List[str],
    float,
    float,
    int,
    int,
    List[str],
]:
    """Analyze evaluation results stored in metadata files.

    Reads the EvaluationResult structure from metadata to determine final status.
    Returns web statistics, categorized task IDs, total run cost, and total eval cost.
    """
    web_to_tasks = defaultdict(list)
    for task_data in task_dict.values():
        web_to_tasks[task_data["web_name"]].append(task_data)

    # Initialize lists for final categorization
    all_successful_ids: List[str] = []
    all_failed_ids: List[str] = []
    all_error_ids: List[str] = []  # Tasks ending in error state
    all_initially_unclear_ids: List[str] = []  # Added: Tasks initially unclear

    # Track costs separately
    total_run_cost = 0.0
    total_eval_cost = 0.0
    total_processed_tasks = 0
    web_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(list))

    task_ids_processed = set()
    # --- Track initial unclear transitions ---
    unclear_initially_now_success = 0
    unclear_initially_now_failed = 0
    # ---------------------------------------

    for web, tasks in web_to_tasks.items():
        web_iterations: List[int] = []
        web_run_costs: List[float] = []
        web_total_eval_costs: List[float] = []
        web_final_successful_count = 0
        web_tasks_processed_count = 0

        for task_data in tasks:
            task_id = task_data["id"]
            if (
                task_id in task_ids_processed
            ):  # Avoid double counting if task_dict has duplicates
                continue
            task_ids_processed.add(task_id)

            result = _process_single_task(task_id, results_dir)

            # Increment counts only if metadata existed, even if processing failed later
            if result.metadata_exists:
                web_tasks_processed_count += 1
                total_processed_tasks += 1

            if result.status == "ok":
                # --- Accumulate Stats for successful processing ---
                # Accumulate costs into separate totals
                total_run_cost += result.run_cost
                web_run_costs.append(result.run_cost)

                # Add total eval cost if it exists
                if result.total_eval_cost > 0:  # Check cost is positive
                    total_eval_cost += result.total_eval_cost
                    web_total_eval_costs.append(result.total_eval_cost)

                if result.iterations is not None:
                    web_iterations.append(result.iterations)

                # --- Categorize Task Based on Final Verdict ---
                if result.final_verdict == "success":
                    all_successful_ids.append(task_id)
                    web_final_successful_count += 1
                elif result.final_verdict == "failed":
                    all_failed_ids.append(task_id)
                elif result.final_verdict == "error":
                    all_error_ids.append(task_id)
                else:
                    # Should not happen if verdicts are constrained
                    print(
                        f"Warning: Unknown final verdict '{result.final_verdict}' for task {task_id}. Marking as error."
                    )
                    all_error_ids.append(task_id)  # Fallback to error category

                # --- Track transitions from unclear ---
                if result.initial_verdict == "unclear":
                    if result.final_verdict == "success":
                        unclear_initially_now_success += 1
                    elif result.final_verdict == "failed":
                        unclear_initially_now_failed += 1
                # -------------------------------------

                # --- Track initially unclear tasks ---
                if result.initial_verdict == "unclear":
                    all_initially_unclear_ids.append(task_id)
                # -------------------------------------

            else:
                # Handle cases where processing failed (file not found, json error, etc.)
                # These are already logged by _process_single_task
                all_error_ids.append(task_id)

        # --- Calculate Website Statistics using Helper ---
        current_web_task_ids = [t["id"] for t in tasks if t["id"] in task_ids_processed]

        web_stats[web] = _calculate_web_stats(
            web_name=web,
            task_ids=current_web_task_ids,  # Pass the list of task IDs for this web
            iterations=web_iterations,
            run_costs=web_run_costs,
            total_eval_costs=web_total_eval_costs,
            successful_count=web_final_successful_count,
            processed_count=web_tasks_processed_count,
            all_error_ids=all_error_ids,  # Pass the master list of errors
        )

    # final_successful_count removed
    # Ensure uniqueness just in case (though should be unique due to task_ids_processed set)
    all_successful_ids = list(set(all_successful_ids))
    all_failed_ids = list(set(all_failed_ids))
    all_error_ids = list(set(all_error_ids))
    all_initially_unclear_ids = list(set(all_initially_unclear_ids))  # Added

    # Sanity check counts
    total_categorized = (
        len(all_successful_ids) + len(all_failed_ids) + len(all_error_ids)
    )
    if total_categorized != total_processed_tasks:
        print(
            f"Warning: Mismatch between total processed tasks ({total_processed_tasks}) and total categorized ({total_categorized})."
        )

    return (
        dict(web_stats),  # Convert back from defaultdict
        all_successful_ids,
        all_failed_ids,
        all_error_ids,
        total_run_cost,
        total_eval_cost,
        unclear_initially_now_success,  # Add new counts to return
        unclear_initially_now_failed,  # Add new counts to return
        all_initially_unclear_ids,  # Added
    )


def save_results_summary(
    results_dir: str,
    web_stats: Dict[str, Dict[str, Any]],
    total_processed_tasks: int,
    successful_task_ids: List[str],
    failed_task_ids: List[str],
    error_task_ids: List[str],
    total_run_cost: float,
    total_eval_cost: float,
    unclear_initially_now_success: int,
    unclear_initially_now_failed: int,
) -> str:
    """Create and save a summary of the results to a text file."""
    # Derive successful count from the passed list
    final_successful_count = len(successful_task_ids)
    success_rate = (
        (final_successful_count / total_processed_tasks * 100)
        if total_processed_tasks > 0
        else 0
    )

    summary_path = os.path.join(results_dir, "results_summary.txt")
    with open(summary_path, "w") as f:
        f.write("WebVoyager Evaluation Results Summary\n")
        f.write("===================================\n\n")
        f.write(
            # Use derived final_successful_count
            f"Overall Final Success Rate: {success_rate:.2f}% ({final_successful_count}/{total_processed_tasks} tasks processed)\n"
        )
        f.write(
            f"Total successful tasks (final): {final_successful_count}\n"
        )  # Use derived count
        f.write(f"Total failed tasks (final): {len(failed_task_ids)}\n")
        f.write(f"Total tasks with errors: {len(error_task_ids)}\n")

        # --- Add unclear transition counts ---
        f.write(
            f"  (Tasks initially 'unclear' resolved to 'success': {unclear_initially_now_success})\n"
        )
        f.write(
            f"  (Tasks initially 'unclear' resolved to 'failed': {unclear_initially_now_failed})\n\n"
        )
        # ------------------------------------

        f.write("Final Success Rates & Stats by Website:\n")
        f.write("---------------------------------------\n")
        # Sort websites by success rate for better readability
        sorted_webs = sorted(
            web_stats.items(), key=lambda x: x[1].get("success_rate", 0.0), reverse=True
        )
        for web, stats in sorted_webs:
            success_rate = stats.get("success_rate", 0.0)
            final_success = stats.get("final_successful_tasks", 0)
            total_processed = stats.get("total_tasks_processed", 0)
            f.write(
                f"{web}: {success_rate:.2f}% ({final_success}/{total_processed} tasks)"
            )
            # Add iteration/cost stats if available
            avg_iter = stats.get("avg_iterations")
            std_dev_iter = stats.get("std_dev_iterations")
            avg_run_cost = stats.get("avg_run_cost", 0.0)
            avg_total_eval_cost = stats.get("avg_total_eval_cost")
            web_error_count = stats.get("error_count", 0)

            stat_parts = []
            if avg_iter is not None and std_dev_iter is not None:
                stat_parts.append(f"Avg Iter: {avg_iter:.2f} (± {std_dev_iter:.2f})")
            if avg_run_cost is not None:
                stat_parts.append(f"Avg Run Cost: ${avg_run_cost:.4f}")
            if avg_total_eval_cost is not None:
                stat_parts.append(f"Avg Total Eval Cost: ${avg_total_eval_cost:.4f}")
            stat_parts.append(f"Errors: {web_error_count}")

            if stat_parts:
                f.write(f"  [{', '.join(stat_parts)}]")
            f.write("\n")

        f.write("\nTotal Run & Evaluation Cost:\n")
        f.write("----------------------------\n")
        # Write separate costs
        f.write(f"Total Run Cost: ${total_run_cost:.6f}\n")
        f.write(f"Total Eval Cost: ${total_eval_cost:.6f}\n")

    return summary_path


def run_aggregation(results_dir_name: str, task_definitions_path: str) -> None:
    """Main function to aggregate and analyze WebVoyager evaluation results."""
    results_abs_path = os.path.abspath(f"runs/{results_dir_name}")
    print(f"Aggregating results from: {results_abs_path}")

    # Load WebVoyager data to get task details
    task_dict = load_task_dict(task_definitions_path)

    # Analyze results
    (
        web_stats,
        final_successful_ids,
        final_failed_ids,
        final_error_ids,
        total_run_cost,
        total_eval_cost,
        unclear_initially_now_success,
        unclear_initially_now_failed,
        all_initially_unclear_ids,
    ) = analyze_results(task_dict, results_abs_path)

    total_processed_tasks = (
        len(final_successful_ids) + len(final_failed_ids) + len(final_error_ids)
    )

    final_successful_count = len(final_successful_ids)

    print(f"Total tasks processed (based on metadata files): {total_processed_tasks}")
    print(
        # Use final_successful_count derived from list length
        f"\nOverall Final Success Rate: {(final_successful_count / total_processed_tasks * 100) if total_processed_tasks > 0 else 0:.2f}% ({final_successful_count}/{total_processed_tasks} tasks)"
    )
    print(
        f"Total successful tasks (final): {final_successful_count}"
    )  # Use derived count
    print(f"Total failed tasks (final): {len(final_failed_ids)}")
    print(f"Total tasks with errors (final): {len(final_error_ids)}")

    # --- Print unclear transition counts ---
    print(f"Total tasks initially deemed 'unclear': {len(all_initially_unclear_ids)}")
    print(
        f"  (Tasks initially 'unclear' resolved to 'success': {unclear_initially_now_success})"
    )
    print(
        f"  (Tasks initially 'unclear' resolved to 'failed': {unclear_initially_now_failed})"
    )
    # ------------------------------------

    # Save tasks details by FINAL status
    successful_path = save_tasks_to_jsonl(
        os.path.join(results_abs_path, "final_successful_tasks.jsonl"),
        final_successful_ids,
        task_dict,
    )
    print(
        f"Saved {len(final_successful_ids)} final successful tasks to {successful_path}"
    )

    failed_path = save_tasks_to_jsonl(
        os.path.join(results_abs_path, "final_failed_tasks.jsonl"),
        final_failed_ids,
        task_dict,
    )
    print(f"Saved {len(final_failed_ids)} final failed tasks to {failed_path}")

    error_path = save_tasks_to_jsonl(
        os.path.join(results_abs_path, "final_error_tasks.jsonl"),
        final_error_ids,
        task_dict,
    )
    print(f"Saved {len(final_error_ids)} final error tasks to {error_path}")

    # --- Save initially unclear tasks ---
    initially_unclear_path = save_tasks_to_jsonl(
        os.path.join(results_abs_path, "initial_unclear_tasks.jsonl"),
        all_initially_unclear_ids,
        task_dict,
    )
    print(
        f"Saved {len(all_initially_unclear_ids)} initially unclear tasks to {initially_unclear_path}"
    )
    # ----------------------------------

    # Save results summary
    summary_path = save_results_summary(
        results_abs_path,
        web_stats,
        total_processed_tasks,
        final_successful_ids,
        final_failed_ids,
        final_error_ids,
        total_run_cost,
        total_eval_cost,
        unclear_initially_now_success,
        unclear_initially_now_failed,
    )
    print(f"Saved results summary to {summary_path}")
