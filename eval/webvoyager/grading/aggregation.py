import json
import os
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from ..utils.file_io import load_task_dict, save_tasks_to_jsonl
from ..utils.types import Metadata, TaskData


def analyze_results(
    task_dict: Dict[str, TaskData],
    results_dir: str,
) -> Tuple[
    Dict[str, Dict[str, Any]], List[str], List[str], List[str], List[str], int, float
]:
    """Analyze evaluation results for all websites.

    Returns:
        Tuple containing:
        - web_stats: Dictionary with detailed stats per website.
        - all_successful_tasks: List of successful task IDs.
        - all_failed_tasks: List of failed task IDs.
        - all_unclear_tasks: List of initially unclear task IDs.
        - all_error_tasks: List of task IDs that errored during evaluation.
        - final_successful_count: Total count of tasks ultimately successful.
        - total_cost: Total cost across all runs.
    """
    web_to_tasks = defaultdict(list)
    for task_data in task_dict.values():
        web_to_tasks[task_data["web_name"]].append(task_data)

    # Initialize counters and lists
    total_cost = 0
    all_successful_tasks = []
    all_failed_tasks = []
    all_unclear_tasks = []
    all_error_tasks = []
    final_successful_count = 0
    total_processed_tasks = 0

    web_stats: Dict[str, Dict[str, Any]] = {}

    # Analyze results for each website
    for web, tasks in web_to_tasks.items():
        web_total_processed = 0
        web_final_successful = 0
        web_initially_successful = []
        web_initially_failed = []
        web_initially_unclear = []
        web_errors = []
        web_iterations = []
        web_run_costs = []
        web_eval_costs = []

        for task_data in tasks:
            task_id = task_data["id"]
            metadata_path = os.path.join(results_dir, task_id, "metadata.json")

            if os.path.exists(metadata_path):
                web_total_processed += 1
                total_processed_tasks += 1

                try:
                    with open(metadata_path) as fr:
                        metadata: Metadata = json.load(fr)

                    # Accumulate costs
                    total_cost += metadata.get("run_cost", 0)
                    web_run_costs.append(metadata.get("run_cost", 0))
                    if metadata.get("auto_eval"):
                        eval_cost = metadata["auto_eval"].get("eval_cost", 0)  # type: ignore
                        total_cost += eval_cost
                        web_eval_costs.append(eval_cost)
                    # Add re-evaluation cost if needed later

                    # Iterations
                    if "iterations" in metadata:
                        web_iterations.append(metadata["iterations"])

                    # Determine final verdict
                    initial_eval = metadata.get("auto_eval")
                    reeval_verdict = metadata.get(
                        "verdict_after_additional_verification"
                    )

                    final_verdict = "error"  # Default if no eval info
                    if initial_eval:
                        initial_verdict = initial_eval.get("verdict")
                        if initial_verdict == "success":
                            final_verdict = "success"
                            web_initially_successful.append(task_id)
                            all_successful_tasks.append(task_id)
                        elif initial_verdict == "failed":
                            final_verdict = "failed"
                            web_initially_failed.append(task_id)
                            all_failed_tasks.append(task_id)
                        elif initial_verdict == "unclear":
                            web_initially_unclear.append(task_id)
                            all_unclear_tasks.append(task_id)
                            if reeval_verdict == "success":
                                final_verdict = "success"
                                # Task moved from unclear to successful
                            elif reeval_verdict == "failed":
                                final_verdict = "failed"
                                # Task moved from unclear to failed
                                all_failed_tasks.append(task_id)  # Add to failed list
                            elif reeval_verdict == "error":
                                final_verdict = "error"  # Error during re-eval
                                web_errors.append(task_id)
                                all_error_tasks.append(task_id)
                            else:
                                # Remains unclear if re-eval didn't run or had no verdict
                                final_verdict = "unclear"
                        elif initial_verdict == "error":
                            final_verdict = "error"
                            web_errors.append(task_id)
                            all_error_tasks.append(task_id)
                    elif (
                        reeval_verdict
                    ):  # Case where initial eval might have failed but re-eval ran
                        if reeval_verdict == "success":
                            final_verdict = "success"
                        elif reeval_verdict == "failed":
                            final_verdict = "failed"
                            all_failed_tasks.append(task_id)
                        elif reeval_verdict == "error":
                            final_verdict = "error"
                            web_errors.append(task_id)
                            all_error_tasks.append(task_id)

                    if final_verdict == "success":
                        web_final_successful += 1
                        final_successful_count += 1
                    elif final_verdict == "error" and task_id not in all_error_tasks:
                        # Catch tasks where metadata existed but eval didn't complete/save properly
                        web_errors.append(task_id)
                        all_error_tasks.append(task_id)

                except json.JSONDecodeError:
                    print(
                        f"Warning: Could not decode JSON from {metadata_path}. Marking as error."
                    )
                    web_errors.append(task_id)
                    all_error_tasks.append(task_id)
                    web_total_processed += 1  # Count as processed even if erroring
                    total_processed_tasks += 1
                except Exception as e:
                    print(
                        f"Warning: Error processing {metadata_path}: {e}. Marking as error."
                    )
                    web_errors.append(task_id)
                    all_error_tasks.append(task_id)
                    web_total_processed += 1  # Count as processed even if erroring
                    total_processed_tasks += 1

        # Calculate stats for this website
        avg_iterations = statistics.mean(web_iterations) if web_iterations else None
        std_dev_iterations = (
            statistics.stdev(web_iterations) if len(web_iterations) > 1 else 0.0
        )
        avg_run_cost = statistics.mean(web_run_costs) if web_run_costs else 0.0
        avg_eval_cost = statistics.mean(web_eval_costs) if web_eval_costs else 0.0

        if web_total_processed > 0:
            web_success_rate = web_final_successful / web_total_processed * 100
            web_stats[web] = {
                "success_rate": web_success_rate,
                "final_successful_tasks": web_final_successful,
                "total_tasks_processed": web_total_processed,
                "initially_successful_ids": web_initially_successful,
                "initially_failed_ids": web_initially_failed,
                "initially_unclear_ids": web_initially_unclear,
                "error_ids": web_errors,
                "avg_iterations": avg_iterations,
                "std_dev_iterations": std_dev_iterations,
                "avg_run_cost": avg_run_cost,
                "avg_eval_cost": avg_eval_cost,
            }
            print(
                f"{web} Final Success Rate: {web_success_rate:.2f}% ({web_final_successful}/{web_total_processed} tasks)"
            )
            if avg_iterations is not None:
                print(
                    f"  Avg Iterations: {avg_iterations:.2f} (± {std_dev_iterations:.2f})"
                )
            print(
                f"  Avg Run Cost: ${avg_run_cost:.6f}, Avg Eval Cost: ${avg_eval_cost:.6f}"
            )
            print(f"  Errors: {len(web_errors)}")

    return (
        web_stats,
        list(
            set(all_successful_tasks)
        ),  # Use set to ensure unique IDs if added multiple times
        list(set(all_failed_tasks)),
        list(set(all_unclear_tasks)),
        list(set(all_error_tasks)),
        final_successful_count,
        total_cost,
    )


def save_results_summary(
    results_dir: str,
    web_stats: Dict[str, Dict[str, Any]],
    final_successful_count: int,
    total_processed_tasks: int,
    successful_task_ids: List[str],
    failed_task_ids: List[str],
    unclear_task_ids: List[str],
    error_task_ids: List[str],
    total_cost: float,
) -> str:
    """Create and save a summary of the results to a text file."""
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
            f"Overall Final Success Rate: {success_rate:.2f}% ({final_successful_count}/{total_processed_tasks} tasks processed)\n"
        )
        f.write(f"Total successful tasks (final): {len(successful_task_ids)}\n")
        f.write(f"Total failed tasks (final): {len(failed_task_ids)}\n")
        f.write(
            f"Total unclear tasks (after re-eval): {len(unclear_task_ids)}\n"
        )  # Tasks that remained unclear
        f.write(f"Total tasks with errors: {len(error_task_ids)}\n\n")

        f.write("Final Success Rates & Stats by Website:\n")
        f.write("---------------------------------------\n")
        # Sort websites by success rate for better readability
        sorted_webs = sorted(
            web_stats.items(), key=lambda x: x[1]["success_rate"], reverse=True
        )
        for web, stats in sorted_webs:
            f.write(
                f"{web}: {stats['success_rate']:.2f}% ({stats['final_successful_tasks']}/{stats['total_tasks_processed']} tasks)"
            )
            # Add iteration/cost stats if available
            avg_iter = stats.get("avg_iterations")
            std_dev_iter = stats.get("std_dev_iterations")
            avg_run_cost = stats.get("avg_run_cost", 0)
            avg_eval_cost = stats.get("avg_eval_cost", 0)
            errors = len(stats.get("error_ids", []))

            stat_parts = []
            if avg_iter is not None and std_dev_iter is not None:
                stat_parts.append(f"Avg Iter: {avg_iter:.2f} (± {std_dev_iter:.2f})")
            stat_parts.append(f"Avg Run Cost: ${avg_run_cost:.4f}")
            stat_parts.append(f"Avg Eval Cost: ${avg_eval_cost:.4f}")
            stat_parts.append(f"Errors: {errors}")

            if stat_parts:
                f.write(f"  [{', '.join(stat_parts)}]")
            f.write("\n")

        f.write("\nTotal Run & Evaluation Cost:\n")
        f.write("----------------------------\n")
        f.write(f"${total_cost:.6f}\n")

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
        successful_task_ids,
        failed_task_ids,
        unclear_task_ids,  # These are tasks *initially* marked unclear
        error_task_ids,
        final_successful_count,
        total_cost,
    ) = analyze_results(task_dict, results_abs_path)

    # Calculate final counts based on IDs collected during analysis
    total_processed_tasks = (
        len(successful_task_ids)
        + len(failed_task_ids)
        + len(unclear_task_ids)
        + len(error_task_ids)
    )
    # Note: unclear_task_ids now represents tasks that *remained* unclear or errored during re-eval
    # Need to refine analyze_results to return the final status lists correctly.
    # For now, saving based on the lists returned by analyze_results.

    # Refine status lists based on final verdict (addressing TODO)
    final_successful_ids = []
    final_failed_ids = []
    final_unclear_ids = []  # Tasks that ended up unclear (initial unclear + no re-eval verdict)
    final_error_ids = list(error_task_ids)  # Start with processing errors

    all_processed_ids = (
        set(successful_task_ids)
        | set(failed_task_ids)
        | set(unclear_task_ids)
        | set(error_task_ids)
    )

    for task_id in all_processed_ids:
        metadata_path = os.path.join(results_abs_path, task_id, "metadata.json")
        if not os.path.exists(metadata_path):
            if task_id not in final_error_ids:
                final_error_ids.append(task_id)
            continue
        try:
            with open(metadata_path) as fr:
                metadata = json.load(fr)
            initial_eval = metadata.get("auto_eval")
            reeval_verdict = metadata.get("verdict_after_additional_verification")

            if reeval_verdict == "success":
                final_successful_ids.append(task_id)
            elif reeval_verdict == "failed":
                final_failed_ids.append(task_id)
            elif initial_eval:
                initial_verdict = initial_eval.get("verdict")
                if initial_verdict == "success":
                    final_successful_ids.append(task_id)
                elif initial_verdict == "failed":
                    final_failed_ids.append(task_id)
                elif initial_verdict == "unclear":
                    # If re-eval verdict is missing or error, it remains unclear/error
                    if reeval_verdict == "error":
                        if task_id not in final_error_ids:
                            final_error_ids.append(task_id)
                    elif reeval_verdict is None:  # No re-evaluation happened or saved
                        final_unclear_ids.append(task_id)
                    # Otherwise handled by reeval_verdict checks above
                elif initial_verdict == "error":
                    if task_id not in final_error_ids:
                        final_error_ids.append(task_id)
            elif (
                reeval_verdict == "error"
            ):  # Error during re-eval, initial might be missing
                if task_id not in final_error_ids:
                    final_error_ids.append(task_id)
            else:
                # Default case: No clear verdict from initial or re-eval -> error
                print(
                    f"Warning: Task {task_id} has ambiguous final state. Marking as error."
                )
                if task_id not in final_error_ids:
                    final_error_ids.append(task_id)

        except Exception as e:
            print(
                f"Error processing metadata for final status determination ({task_id}): {e}"
            )
            if task_id not in final_error_ids:
                final_error_ids.append(task_id)

    # Use unique lists
    final_successful_ids = list(set(final_successful_ids))
    final_failed_ids = list(set(final_failed_ids))
    final_unclear_ids = list(set(final_unclear_ids))
    final_error_ids = list(set(final_error_ids))

    # Recalculate total processed based on final categorization
    total_final_categorized = (
        len(final_successful_ids)
        + len(final_failed_ids)
        + len(final_unclear_ids)
        + len(final_error_ids)
    )
    print(f"Total tasks processed (based on metadata files): {total_processed_tasks}")
    print(f"Total tasks categorized into final states: {total_final_categorized}")
    if total_processed_tasks != total_final_categorized:
        print(
            "Warning: Discrepancy between processed tasks count and final categorized count."
        )

    print(
        f"\nOverall Final Success Rate: {(len(final_successful_ids) / total_final_categorized * 100) if total_final_categorized > 0 else 0:.2f}% ({len(final_successful_ids)}/{total_final_categorized} tasks)"
    )
    print(f"Total successful tasks (final): {len(final_successful_ids)}")
    print(f"Total failed tasks (final): {len(final_failed_ids)}")
    print(f"Total unclear tasks (final): {len(final_unclear_ids)}")
    print(f"Total tasks with errors (final): {len(final_error_ids)}")

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

    unclear_path = save_tasks_to_jsonl(
        os.path.join(results_abs_path, "final_unclear_tasks.jsonl"),
        final_unclear_ids,
        task_dict,
    )
    print(f"Saved {len(final_unclear_ids)} final unclear tasks to {unclear_path}")

    error_path = save_tasks_to_jsonl(
        os.path.join(results_abs_path, "final_error_tasks.jsonl"),
        final_error_ids,
        task_dict,
    )
    print(f"Saved {len(final_error_ids)} final error tasks to {error_path}")

    # Save results summary
    summary_path = save_results_summary(
        results_abs_path,
        web_stats,
        len(final_successful_ids),  # Use final count
        total_final_categorized,  # Use final count
        final_successful_ids,
        final_failed_ids,
        final_unclear_ids,
        final_error_ids,
        total_cost,
    )
    print(f"Saved results summary to {summary_path}")
