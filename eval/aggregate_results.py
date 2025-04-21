import argparse
import json
import os
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
) -> Tuple[Dict[str, Dict[str, Any]], List[str], int, int]:
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

    # Initialize counters
    total_tasks = 0
    successful_tasks = 0
    web_success_rates = {}
    all_failed_tasks = []

    # Analyze results for each website
    for web in webs:
        web_total_tasks = 0
        web_successful_tasks = 0
        successful_file_dirs = []
        failed_file_dirs = []

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

                auto_eval_res = metadata.get("auto_eval", {})
                if auto_eval_res:
                    verdict = auto_eval_res.get("verdict", "unknown")
                    if verdict == "success":
                        web_successful_tasks += 1
                        successful_tasks += 1
                        successful_file_dirs.append(file_dir)
                    else:
                        failed_file_dirs.append(file_dir)
                        all_failed_tasks.append(task_id)

        # Calculate success rate for this website
        if web_total_tasks > 0:
            web_success_rate = web_successful_tasks / web_total_tasks * 100
            web_success_rates[web] = {
                "success_rate": web_success_rate,
                "successful_tasks": web_successful_tasks,
                "total_tasks": web_total_tasks,
                "successful_file_dirs": successful_file_dirs,
                "failed_file_dirs": failed_file_dirs,
            }
            print(
                f"{web} Success Rate: {web_success_rate:.2f}% ({web_successful_tasks}/{web_total_tasks} tasks)"
            )

    return web_success_rates, all_failed_tasks, successful_tasks, total_tasks


def save_failed_tasks(
    results_dir: str, all_failed_tasks: List[str], task_dict: Dict[str, Dict[str, Any]]
) -> str:
    """Save details of failed tasks to a JSONL file."""
    failed_tasks_details = []
    for task_id in all_failed_tasks:
        if task_id in task_dict:
            failed_tasks_details.append(task_dict[task_id])
        else:
            print(f"Warning: Task ID {task_id} not found in WebVoyager data")

    # Save failed tasks to a JSONL file
    output_path = os.path.join(results_dir, "failed_tasks.jsonl")
    with open(output_path, "w") as f:
        for task in failed_tasks_details:
            f.write(json.dumps(task) + "\n")

    return output_path


def save_results_summary(
    results_dir: str,
    web_success_rates: Dict[str, Dict[str, Any]],
    successful_tasks: int,
    total_tasks: int,
    all_failed_tasks: List[str],
) -> str:
    """Create and save a summary of the results to a text file."""
    success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0

    summary_path = os.path.join(results_dir, "results_summary.txt")
    with open(summary_path, "w") as f:
        f.write("WebVoyager Evaluation Results Summary\n")
        f.write("===================================\n\n")
        f.write(
            f"Overall Success Rate: {success_rate:.2f}% ({successful_tasks}/{total_tasks} tasks)\n"
        )
        f.write(f"Total failed tasks: {len(all_failed_tasks)}\n\n")

        f.write("Success Rates by Website:\n")
        f.write("------------------------\n")
        # Sort websites by success rate for better readability
        sorted_webs = sorted(
            web_success_rates.items(), key=lambda x: x[1]["success_rate"], reverse=True
        )
        for web, stats in sorted_webs:
            f.write(
                f"{web}: {stats['success_rate']:.2f}% ({stats['successful_tasks']}/{stats['total_tasks']} tasks)\n"
            )

    return summary_path


def main() -> None:
    """Main function to aggregate and analyze WebVoyager evaluation results."""
    args = parse_arguments()

    # Load WebVoyager data to get task details

    task_dict = load_task_data("eval/WebVoyager_data.jsonl")

    # Analyze results
    web_success_rates, all_failed_tasks, successful_tasks, total_tasks = (
        analyze_results(args.results_dir)
    )

    # Calculate and display the overall success rate
    success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0
    print(
        f"\nOverall Success Rate: {success_rate:.2f}% ({successful_tasks}/{total_tasks} tasks)"
    )
    print(f"Total failed tasks: {len(all_failed_tasks)}")

    # Save failed tasks details
    output_path = save_failed_tasks(args.results_dir, all_failed_tasks, task_dict)
    print(f"Saved {len(all_failed_tasks)} failed tasks to {output_path}")

    # Save results summary
    summary_path = save_results_summary(
        args.results_dir,
        web_success_rates,
        successful_tasks,
        total_tasks,
        all_failed_tasks,
    )
    print(f"Saved results summary to {summary_path}")


if __name__ == "__main__":
    main()
