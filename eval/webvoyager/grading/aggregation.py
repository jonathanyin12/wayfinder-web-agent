import json
import os
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from ..utils.file_io import load_task_dict, save_tasks_to_jsonl
from ..utils.types import Evaluation, EvaluationResult, Metadata, TaskData


def analyze_results(
    task_dict: Dict[str, TaskData],
    results_dir: str,
) -> Tuple[
    Dict[str, Dict[str, Any]], List[str], List[str], List[str], List[str], int, float
]:
    """Analyze evaluation results stored in metadata files.

    Reads the EvaluationResult structure from metadata to determine final status.
    """
    web_to_tasks = defaultdict(list)
    for task_data in task_dict.values():
        web_to_tasks[task_data["web_name"]].append(task_data)

    # Initialize lists for final categorization
    all_successful_ids: List[str] = []
    all_failed_ids: List[str] = []
    all_unclear_ids: List[str] = []  # Tasks ending in unclear state
    all_error_ids: List[str] = []  # Tasks ending in error state

    total_cost = 0.0
    total_processed_tasks = 0
    web_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(list))

    task_ids_processed = set()

    for web, tasks in web_to_tasks.items():
        web_iterations: List[int] = []
        web_run_costs: List[float] = []
        web_eval_costs: List[float] = []
        web_reeval_costs: List[float] = []
        web_final_successful_count = 0
        web_tasks_processed_count = 0

        for task_data in tasks:
            task_id = task_data["id"]
            if (
                task_id in task_ids_processed
            ):  # Avoid double counting if task_dict has duplicates
                continue
            task_ids_processed.add(task_id)

            metadata_path = os.path.join(results_dir, task_id, "metadata.json")
            final_verdict = "error"  # Default status
            metadata: Metadata | None = None  # Allow None initially

            if not os.path.exists(metadata_path):
                print(
                    f"Warning: Metadata file not found for task {task_id}. Marking as error."
                )
                final_verdict = "error"
                # Decide whether to increment total_processed_tasks here or not
            else:
                # Metadata file exists, try loading
                try:
                    with open(metadata_path) as fr:
                        # Assign and type hint here, guaranteed non-None if load succeeds
                        loaded_metadata: Metadata = json.load(fr)
                    metadata = loaded_metadata  # Assign to outer scope var if needed later, or just use loaded_metadata

                    web_tasks_processed_count += 1
                    total_processed_tasks += 1

                    # --- Cost Calculation (using loaded_metadata) ---
                    run_cost = loaded_metadata.get("run_cost", 0.0)
                    total_cost += run_cost
                    web_run_costs.append(run_cost)

                    evaluation_result = loaded_metadata.get("evaluation_result")
                    eval_cost = 0.0
                    reeval_cost = 0.0

                    if evaluation_result:
                        initial_eval = evaluation_result.get("evaluation")
                        re_eval = evaluation_result.get("re_evaluation")
                        if initial_eval:
                            eval_cost = initial_eval.get("eval_cost", 0.0)
                            total_cost += eval_cost
                            web_eval_costs.append(eval_cost)
                        if re_eval:
                            reeval_cost = re_eval.get("eval_cost", 0.0)
                            total_cost += reeval_cost
                            web_reeval_costs.append(reeval_cost)

                        # --- Final Verdict Determination ---
                        final_verdict = evaluation_result.get("final_verdict", "error")

                    else:
                        # No evaluation result found in metadata
                        final_verdict = "error"
                        print(f"Warning: No evaluation_result found for {task_id}.")

                    # --- Iteration Count (using loaded_metadata) ---
                    if "iterations" in loaded_metadata:
                        web_iterations.append(loaded_metadata["iterations"])

                except json.JSONDecodeError:
                    print(
                        f"Warning: Could not decode JSON from {metadata_path}. Marking as error."
                    )
                    final_verdict = "error"
                    # Count as processed because the file existed but was invalid
                    web_tasks_processed_count += 1
                    total_processed_tasks += 1
                except Exception as e:
                    print(
                        f"Warning: Error processing {metadata_path}: {e}. Marking as error."
                    )
                    final_verdict = "error"
                    # Count as processed because the file existed but processing failed
                    web_tasks_processed_count += 1
                    total_processed_tasks += 1

            # --- Categorize Task Based on Final Verdict ---
            if final_verdict == "success":
                all_successful_ids.append(task_id)
                web_final_successful_count += 1
            elif final_verdict == "failed":
                all_failed_ids.append(task_id)
            elif (
                final_verdict == "unclear"
            ):  # Should only happen if initial eval was unclear and re-eval didn't run/error
                all_unclear_ids.append(task_id)
            elif final_verdict == "error":
                all_error_ids.append(task_id)
            else:
                # Should not happen if verdicts are constrained
                print(
                    f"Warning: Unknown final verdict '{final_verdict}' for task {task_id}. Marking as error."
                )
                all_error_ids.append(task_id)

            # Store task counts per website regardless of success/failure for stats
            web_stats[web]["task_ids"].append(task_id)

        # --- Calculate Website Statistics ---
        web_stats[web]["total_tasks_processed"] = web_tasks_processed_count
        web_stats[web]["final_successful_tasks"] = web_final_successful_count

        avg_iterations = statistics.mean(web_iterations) if web_iterations else None
        std_dev_iterations = (
            statistics.stdev(web_iterations) if len(web_iterations) > 1 else 0.0
        )
        web_stats[web]["avg_iterations"] = avg_iterations
        web_stats[web]["std_dev_iterations"] = std_dev_iterations

        web_stats[web]["avg_run_cost"] = (
            statistics.mean(web_run_costs) if web_run_costs else 0.0
        )
        web_stats[web]["avg_eval_cost"] = (
            statistics.mean(web_eval_costs) if web_eval_costs else 0.0
        )
        web_stats[web]["avg_reeval_cost"] = (
            statistics.mean(web_reeval_costs) if web_reeval_costs else 0.0
        )

        if web_tasks_processed_count > 0:
            web_success_rate = (
                web_final_successful_count / web_tasks_processed_count * 100
            )
            web_stats[web]["success_rate"] = web_success_rate
            print(
                f"{web} Final Success Rate: {web_success_rate:.2f}% ({web_final_successful_count}/{web_tasks_processed_count} tasks)"
            )
            stat_line_parts = []
            if avg_iterations is not None:
                stat_line_parts.append(
                    f"Avg Iter: {avg_iterations:.2f} (± {std_dev_iterations:.2f})"
                )
            stat_line_parts.append(
                f"Avg Run Cost: ${web_stats[web]['avg_run_cost']:.4f}"
            )
            stat_line_parts.append(
                f"Avg Eval Cost: ${web_stats[web]['avg_eval_cost']:.4f}"
            )
            if web_reeval_costs:
                stat_line_parts.append(
                    f"Avg ReEval Cost: ${web_stats[web]['avg_reeval_cost']:.4f}"
                )
            # Count errors specifically for this website
            web_error_count = sum(
                1 for tid in web_stats[web]["task_ids"] if tid in all_error_ids
            )
            stat_line_parts.append(f"Errors: {web_error_count}")
            print(f"  [{', '.join(stat_line_parts)}]")
        else:
            web_stats[web]["success_rate"] = 0.0
            print(f"{web}: No tasks processed.")

    final_successful_count = len(all_successful_ids)
    # Ensure uniqueness just in case
    all_successful_ids = list(set(all_successful_ids))
    all_failed_ids = list(set(all_failed_ids))
    all_unclear_ids = list(set(all_unclear_ids))
    all_error_ids = list(set(all_error_ids))

    # Sanity check counts
    total_categorized = (
        len(all_successful_ids)
        + len(all_failed_ids)
        + len(all_unclear_ids)
        + len(all_error_ids)
    )
    if total_categorized != total_processed_tasks:
        print(
            f"Warning: Mismatch between total processed tasks ({total_processed_tasks}) and total categorized ({total_categorized})."
        )

    return (
        dict(web_stats),  # Convert back from defaultdict
        all_successful_ids,
        all_failed_ids,
        all_unclear_ids,
        all_error_ids,
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
        f.write(f"Total unclear tasks (final): {len(unclear_task_ids)}\n")
        f.write(f"Total tasks with errors: {len(error_task_ids)}\n\n")

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
            avg_eval_cost = stats.get("avg_eval_cost", 0.0)
            avg_reeval_cost = stats.get("avg_reeval_cost")
            web_error_count = sum(
                1 for tid in stats.get("task_ids", []) if tid in error_task_ids
            )

            stat_parts = []
            if avg_iter is not None and std_dev_iter is not None:
                stat_parts.append(f"Avg Iter: {avg_iter:.2f} (± {std_dev_iter:.2f})")
            stat_parts.append(f"Avg Run Cost: ${avg_run_cost:.4f}")
            stat_parts.append(f"Avg Eval Cost: ${avg_eval_cost:.4f}")
            if avg_reeval_cost is not None:
                stat_parts.append(f"Avg ReEval Cost: ${avg_reeval_cost:.4f}")
            stat_parts.append(f"Errors: {web_error_count}")

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

    # Analyze results - This now directly gives final categorization
    (
        web_stats,
        final_successful_ids,
        final_failed_ids,
        final_unclear_ids,
        final_error_ids,
        final_successful_count,
        total_cost,
    ) = analyze_results(task_dict, results_abs_path)

    total_processed_tasks = (
        len(final_successful_ids)
        + len(final_failed_ids)
        + len(final_unclear_ids)
        + len(final_error_ids)
    )

    print(f"Total tasks processed (based on metadata files): {total_processed_tasks}")
    print(
        f"\nOverall Final Success Rate: {(final_successful_count / total_processed_tasks * 100) if total_processed_tasks > 0 else 0:.2f}% ({final_successful_count}/{total_processed_tasks} tasks)"
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
        final_successful_count,
        total_processed_tasks,
        final_successful_ids,
        final_failed_ids,
        final_unclear_ids,
        final_error_ids,
        total_cost,
    )
    print(f"Saved results summary to {summary_path}")
