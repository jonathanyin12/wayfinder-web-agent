import asyncio
import json
from typing import Any, Tuple

from openai import AsyncAzureOpenAI, AsyncOpenAI

from ..utils.file_io import load_task_metadata, save_task_metadata
from ..utils.llm_interface import (
    call_llm,
    prepare_initial_evaluation_messages,
    prepare_reevaluation_prompt,
    process_llm_response,
)
from ..utils.types import EvaluationResult, Metadata, ReEvaluationResult


async def evaluate_task_initial(
    semaphore: asyncio.Semaphore,
    process_dir: str,
    openai_client: AsyncOpenAI | AsyncAzureOpenAI,
    model: str,
    img_num: int,
) -> Tuple[str, str | None, float, Metadata | None]:
    """Evaluates a single task using screenshots and response.

    Returns:
        Tuple containing: (verdict, explanation, cost, updated_metadata or None on error)
    """
    async with semaphore:
        print(
            f"--------------------- Initial Eval: {process_dir} ---------------------"
        )
        try:
            metadata = load_task_metadata(process_dir)
            messages = prepare_initial_evaluation_messages(
                metadata, process_dir, img_num
            )
            response_content, cost = await call_llm(
                openai_client, model, messages=messages, json_mode=True
            )
            evaluation_data = process_llm_response(response_content, cost, model)

            # Ensure the response conforms to EvaluationResult structure (basic check)
            if "verdict" not in evaluation_data or "explanation" not in evaluation_data:
                raise ValueError(
                    "LLM response missing required fields 'verdict' or 'explanation'."
                )

            # Cast to the specific type (assuming validation passes)
            evaluation_result: EvaluationResult = evaluation_data  # type: ignore

            verdict = evaluation_result["verdict"]
            explanation = evaluation_result["explanation"]
            print(f"Initial Verdict: {verdict}")
            print(f"Explanation: {explanation}")

            # Save evaluation result to metadata
            metadata["auto_eval"] = evaluation_result
            save_task_metadata(process_dir, metadata)

            return verdict, explanation, cost, metadata

        except FileNotFoundError:
            print(f"Metadata file not found in {process_dir}. Skipping initial eval.")
            return "error", f"Metadata file not found: {process_dir}", 0.0, None
        except json.JSONDecodeError:
            print(
                f"Invalid JSON in metadata file for {process_dir}. Skipping initial eval."
            )
            return "error", f"Invalid JSON in metadata: {process_dir}", 0.0, None
        except Exception as e:
            print(
                f"An unexpected error occurred during initial eval for {process_dir}: {e}"
            )
            return "error", f"Unexpected error: {e}", 0.0, None


async def evaluate_unclear_task(
    semaphore: asyncio.Semaphore,
    task_id: str,
    metadata: Metadata,
    openai_client: AsyncOpenAI | AsyncAzureOpenAI,
    model: str = "o4-mini",  # Default model for re-evaluation
) -> Tuple[bool, str, Metadata]:
    """Re-evaluates a task previously marked as 'unclear'.

    Returns:
        Tuple containing: (success_bool, explanation, updated_metadata)
    """
    async with semaphore:
        print(
            f"--------------------- Re-evaluating Unclear Task: {task_id} ---------------------"
        )

        try:
            prompt = prepare_reevaluation_prompt(metadata)
            response_content, cost = await call_llm(
                openai_client, model, prompt=prompt, json_mode=True
            )
            # Note: Cost from re-evaluation is currently not stored, but could be added.
            response_json = process_llm_response(response_content, cost, model)

            # Ensure the response conforms to ReEvaluationResult structure (basic check)
            if "verdict" not in response_json or "explanation" not in response_json:
                raise ValueError(
                    "LLM re-evaluation response missing required fields 'verdict' or 'explanation'."
                )

            # Cast to the specific type
            reeval_result: ReEvaluationResult = response_json  # type: ignore

            verdict = reeval_result["verdict"].lower()
            explanation = reeval_result["explanation"]
            success = verdict == "success"

            if not success:
                print(f"Re-evaluation Verdict: Failed")
                print(f"  Task: {task_id}")
                print(f"  Final response: {metadata.get('final_response')}")
                # Handle potential None for auto_eval
                original_eval = metadata.get("auto_eval")
                original_explanation = (
                    original_eval.get("explanation") if original_eval else "N/A"
                )
                print(f"  Original Evaluator's Evaluation: {original_explanation}")
                print(f"  Re-evaluation Explanation: {explanation}")
            else:
                print(f"Re-evaluation Verdict: Success")

            # Update metadata with the re-evaluation verdict and reasoning
            metadata["verdict_after_additional_verification"] = (
                "success" if success else "failed"
            )
            metadata["additional_verification_reasoning"] = explanation

            # Save the updated metadata (assuming process_dir can be derived or is passed)
            # This requires knowing the results directory structure.
            # For now, returning the updated metadata to be saved by the caller.
            # process_dir = os.path.join(results_base_dir, task_id) # Example
            # save_task_metadata(process_dir, metadata)

            return success, explanation, metadata

        except Exception as e:
            print(f"Error verifying unclear task {task_id}: {e}")
            # Update metadata to reflect the error during re-evaluation
            metadata["verdict_after_additional_verification"] = "error"
            metadata["additional_verification_reasoning"] = (
                f"Error during re-evaluation: {e}"
            )
            return False, f"Error during re-evaluation: {e}", metadata
