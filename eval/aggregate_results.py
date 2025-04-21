import argparse
import json
import os
import statistics
import sys
from typing import Any, Dict, List, Tuple


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate WebVoyager evaluation results"
    )
    parser.add_argument(
        "results_dir",
        type=str,
        help="Directory containing evaluation results (e.g., 'webvoyager/20250420_171609')",
    )

    return parser.parse_args()


def load_task_data(data_file: str) -> Dict[str, Dict[str, Any]]:
    """Load WebVoyager task data from JSONL file."""
    all_tasks = []
    try:
        with open(data_file, "r") as f:
            for line in f:
                all_tasks.append(json.loads(line))
    except FileNotFoundError:
        print(f"Error: Data file '{data_file}' not found")
        sys.exit(1)

    # Create a dictionary for quick lookup by task ID
    return {task["id"]: task for task in all_tasks}


def analyze_results(
    results_dir: str,
) -> Tuple[Dict[str, Dict[str, Any]], List[str], List[str], List[str], int, int, float]:
    """Analyze evaluation results for all websites."""
    # List of websites to analyze
    webs = [
        "Allrecipes",
        "Amazon",
        "Apple",
        "ArXiv",
        "BBC News",
        "Booking",
        "Cambridge Dictionary",
        "Coursera",
        "ESPN",
        "GitHub",
        "Google Flights",
        "Google Map",
        "Google Search",
        "Huggingface",
        "Wolfram Alpha",
    ]

    # Initialize counters and lists
    total_tasks = 0
    successful_tasks_count = 0
    web_success_rates = {}
    all_successful_tasks = []
    all_failed_tasks = []
    all_unclear_tasks = []  # Fix: Initialize list
    total_cost = 0

    # Analyze results for each website
    for web in webs:
        web_total_tasks = 0
        web_successful_tasks = 0
        successful_file_dirs = []
        failed_file_dirs = []
        unclear_file_dirs = []
        web_iterations = []  # List to store iteration counts for this website
        # Check each possible task ID
        for idx in range(0, 46):
            task_id = f"{web}--{idx}"
            file_dir = os.path.join(results_dir, task_id)
            metadata_file = os.path.join(file_dir, "metadata.json")

            if os.path.exists(metadata_file):
                web_total_tasks += 1
                total_tasks += 1

                with open(metadata_file) as fr:
                    metadata = json.load(fr)

                # Extract token usage data if available
                total_cost += metadata["run_cost"]

                # Extract iteration count if available
                if "iterations" in metadata:
                    web_iterations.append(metadata["iterations"])

                auto_eval_res = metadata.get("auto_eval", {})
                if auto_eval_res:
                    verdict = auto_eval_res.get("verdict", "unknown")
                    if verdict == "success":
                        web_successful_tasks += 1
                        successful_tasks_count += 1
                        successful_file_dirs.append(file_dir)
                        all_successful_tasks.append(
                            task_id
                        )  # Track successful task IDs
                    elif verdict == "failed":
                        failed_file_dirs.append(file_dir)
                        all_failed_tasks.append(task_id)
                    else:  # Includes 'unknown' or any other verdict
                        unclear_file_dirs.append(file_dir)
                        all_unclear_tasks.append(task_id)  # Track unclear task IDs

        # Calculate iteration statistics for this website
        avg_iterations = None
        std_dev_iterations = None
        if web_iterations:
            avg_iterations = statistics.mean(web_iterations)
            if len(web_iterations) > 1:
                try:
                    std_dev_iterations = statistics.stdev(web_iterations)
                except statistics.StatisticsError:
                    std_dev_iterations = 0.0  # Handle case with identical values
            else:
                std_dev_iterations = 0.0  # Std dev is 0 for a single data point

        # Calculate success rate for this website
        if web_total_tasks > 0:
            web_success_rate = web_successful_tasks / web_total_tasks * 100
            web_success_rates[web] = {
                "success_rate": web_success_rate,
                "successful_tasks": web_successful_tasks,
                "total_tasks": web_total_tasks,
                "successful_file_dirs": successful_file_dirs,
                "failed_file_dirs": failed_file_dirs,
                "unclear_file_dirs": unclear_file_dirs,  # Store unclear file dirs
                "avg_iterations": avg_iterations,
                "std_dev_iterations": std_dev_iterations,
            }
            print(
                f"{web} Success Rate: {web_success_rate:.2f}% ({web_successful_tasks}/{web_total_tasks} tasks)"
            )
            if avg_iterations is not None and std_dev_iterations is not None:
                print(
                    f"  Avg Iterations: {avg_iterations:.2f} (± {std_dev_iterations:.2f})"
                )

    return (
        web_success_rates,
        all_successful_tasks,
        all_failed_tasks,
        all_unclear_tasks,
        successful_tasks_count,
        total_tasks,
        total_cost,
    )


def save_tasks_by_status(
    results_dir: str,
    task_ids: List[str],
    task_dict: Dict[str, Dict[str, Any]],
    output_filename: str,
) -> str:
    """Save details of tasks with a specific status to a JSONL file."""
    tasks_details = []
    for task_id in task_ids:
        if task_id in task_dict:
            tasks_details.append(task_dict[task_id])
        else:
            print(f"Warning: Task ID {task_id} not found in WebVoyager data")

    # Save tasks to a JSONL file
    output_path = os.path.join(results_dir, output_filename)
    with open(output_path, "w") as f:
        for task in tasks_details:
            f.write(json.dumps(task) + "\n")

    return output_path


def save_results_summary(
    results_dir: str,
    web_success_rates: Dict[str, Dict[str, Any]],
    successful_tasks_count: int,
    total_tasks: int,
    all_successful_tasks: List[str],
    all_failed_tasks: List[str],
    all_unclear_tasks: List[str],
    total_cost: float,
) -> str:
    """Create and save a summary of the results to a text file."""
    success_rate = (
        (successful_tasks_count / total_tasks * 100) if total_tasks > 0 else 0
    )

    summary_path = os.path.join(results_dir, "results_summary.txt")
    with open(summary_path, "w") as f:
        f.write("WebVoyager Evaluation Results Summary\n")
        f.write("===================================\n\n")
        f.write(
            f"Overall Success Rate: {success_rate:.2f}% ({successful_tasks_count}/{total_tasks} tasks)\n"
        )
        f.write(f"Total successful tasks: {len(all_successful_tasks)}\n")
        f.write(f"Total failed tasks: {len(all_failed_tasks)}\n")
        f.write(f"Total unclear tasks: {len(all_unclear_tasks)}\n\n")

        f.write("Success Rates by Website:\n")
        f.write("------------------------\n")
        # Sort websites by success rate for better readability
        sorted_webs = sorted(
            web_success_rates.items(), key=lambda x: x[1]["success_rate"], reverse=True
        )
        for web, stats in sorted_webs:
            f.write(
                f"{web}: {stats['success_rate']:.2f}% ({stats['successful_tasks']}/{stats['total_tasks']} tasks)"
            )
            # Add iteration stats if available
            avg_iter = stats.get("avg_iterations")
            std_dev_iter = stats.get("std_dev_iterations")
            if avg_iter is not None and std_dev_iter is not None:
                f.write(f"  Avg Iterations: {avg_iter:.2f} (± {std_dev_iter:.2f})")
            f.write("\n")

        f.write("\nTotal cost:\n")
        f.write("-------------\n")
        f.write(f"${total_cost:.6f}\n")

    return summary_path


def main() -> None:
    """Main function to aggregate and analyze WebVoyager evaluation results."""
    args = parse_arguments()

    # Load WebVoyager data to get task details
    task_dict = load_task_data("eval/WebVoyager_data.jsonl")

    # Analyze results
    (
        web_success_rates,
        all_successful_tasks,
        all_failed_tasks,
        all_unclear_tasks,
        successful_tasks_count,
        total_tasks,
        total_cost,
    ) = analyze_results(args.results_dir)

    # Calculate and display the overall success rate and counts
    success_rate = (
        (successful_tasks_count / total_tasks * 100) if total_tasks > 0 else 0
    )
    print(
        f"\nOverall Success Rate: {success_rate:.2f}% ({successful_tasks_count}/{total_tasks} tasks)"
    )
    print(f"Total successful tasks: {len(all_successful_tasks)}")
    print(f"Total failed tasks: {len(all_failed_tasks)}")
    print(f"Total unclear tasks: {len(all_unclear_tasks)}")

    # Save tasks details by status
    successful_path = save_tasks_by_status(
        args.results_dir, all_successful_tasks, task_dict, "successful_tasks.jsonl"
    )
    print(f"Saved {len(all_successful_tasks)} successful tasks to {successful_path}")

    failed_path = save_tasks_by_status(
        args.results_dir, all_failed_tasks, task_dict, "failed_tasks.jsonl"
    )
    print(f"Saved {len(all_failed_tasks)} failed tasks to {failed_path}")

    unclear_path = save_tasks_by_status(
        args.results_dir, all_unclear_tasks, task_dict, "unclear_tasks.jsonl"
    )
    print(f"Saved {len(all_unclear_tasks)} unclear tasks to {unclear_path}")

    # Save results summary
    summary_path = save_results_summary(
        args.results_dir,
        web_success_rates,
        successful_tasks_count,
        total_tasks,
        all_successful_tasks,
        all_failed_tasks,
        all_unclear_tasks,
        total_cost,
    )
    print(f"Saved results summary to {summary_path}")


if __name__ == "__main__":
    main()
