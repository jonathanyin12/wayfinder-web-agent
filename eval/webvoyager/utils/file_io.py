import base64
import json
import os
import sys
from typing import Any, Dict, List

from .types import Metadata, TaskData


def encode_image(image_path):
    """Encodes an image file to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def load_task_metadata(process_dir: str) -> Metadata:
    """Loads metadata from the metadata.json file."""
    metadata_file = os.path.join(process_dir, "metadata.json")
    with open(metadata_file) as fr:
        # TODO: Add validation for the loaded metadata against the Metadata type
        return json.load(fr)


def save_task_metadata(process_dir: str, metadata: Metadata):
    """Saves the metadata back to the metadata.json file."""
    metadata_file = os.path.join(process_dir, "metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)


def load_task_definitions(file_path: str) -> List[TaskData]:
    """Loads task definitions from a JSONL file."""
    tasks = []
    with open(file_path, "r") as f:
        for line in f:
            # Load task data directly
            task_data = json.loads(line)
            tasks.append(task_data)
    return tasks


def load_task_dict(data_file: str) -> Dict[str, TaskData]:
    """Load WebVoyager task data from JSONL file into a dictionary."""
    all_tasks: List[TaskData] = []
    try:
        all_tasks = load_task_definitions(data_file)
    except FileNotFoundError:
        print(f"Error: Task definitions file '{data_file}' not found")
        sys.exit(1)

    # Create a dictionary for quick lookup by task ID
    return {task["id"]: task for task in all_tasks}


def save_tasks_to_jsonl(
    output_path: str,
    task_ids: List[str],
    task_dict: Dict[str, TaskData],
):
    """Save details of specified tasks to a JSONL file."""
    tasks_details = []
    for task_id in task_ids:
        if task_id in task_dict:
            tasks_details.append(task_dict[task_id])
        else:
            print(f"Warning: Task ID {task_id} not found in task dictionary")

    # Save tasks to the JSONL file
    with open(output_path, "w") as f:
        for task in tasks_details:
            f.write(json.dumps(task) + "\n")
