import asyncio
import json

from openai import AsyncAzureOpenAI, AsyncOpenAI

from ..utils.file_io import load_task_metadata, save_task_metadata
from ..utils.llm_interface import (
    call_llm,
    prepare_initial_evaluation_messages,
    prepare_reevaluation_prompt,
    process_llm_response_into_evaluation,
)
from ..utils.types import EvaluationResult, Metadata


async def evaluate_task(
    semaphore: asyncio.Semaphore,
    process_dir: str,
    openai_client: AsyncOpenAI | AsyncAzureOpenAI,
    model: str,
    img_num: int,
) -> None:
    """Evaluates a single task using screenshots and response.

    Updates metadata with EvaluationResult containing the initial evaluation.

    Returns:
        Tuple containing: (verdict or None on error, updated_metadata or None on error)
    """
    async with semaphore:
        print(
            f"--------------------- Initial Eval: {process_dir} ---------------------"
        )
        verdict = None
        metadata = None
        try:
            metadata = load_task_metadata(process_dir)
            messages = prepare_initial_evaluation_messages(
                metadata, process_dir, img_num
            )
            response_content, cost = await call_llm(
                openai_client, model, messages=messages, json_mode=True
            )
            # Process response into an Evaluation structure
            evaluation = process_llm_response_into_evaluation(
                response_content, cost, model
            )

            verdict = evaluation["verdict"]
            print(f"Verdict: {verdict}")
            print(f"Explanation: {evaluation['explanation']}")

            # Start building the evaluation result
            evaluation_result: EvaluationResult = {
                "evaluation": evaluation,
                "re_evaluation": None,  # Default to None
                "final_verdict": verdict,  # Start with initial verdict
            }

            # If initial verdict is unclear, trigger re-evaluation
            # evaluate_unclear_task updates evaluation_result in-place
            if verdict == "unclear":
                await evaluate_unclear_task(
                    process_dir=process_dir,
                    metadata=metadata,
                    openai_client=openai_client,
                    model=model,
                )

            # Save the potentially updated evaluation_result to metadata
            metadata["evaluation_result"] = evaluation_result
            save_task_metadata(process_dir, metadata)

        except FileNotFoundError:
            print(f"Metadata file not found in {process_dir}. Skipping initial eval.")
        except json.JSONDecodeError:
            print(
                f"Invalid JSON in metadata file for {process_dir}. Skipping initial eval."
            )
        except Exception as e:
            print(
                f"An unexpected error occurred during initial eval for {process_dir}: {e}"
            )


async def evaluate_unclear_task(
    process_dir: str,
    metadata: Metadata,
    openai_client: AsyncOpenAI | AsyncAzureOpenAI,
    model: str,
) -> None:
    """Re-evaluates a task previously marked as 'unclear'.

    Updates the 're_evaluation' and 'final_verdict' fields in metadata['evaluation_result'] in-place.

    Returns:
        The final verdict string ("success" or "failed").
    """
    print(f"--------------------- Re-evaluating: {process_dir} ---------------------")
    evaluation_result = metadata["evaluation_result"]
    if evaluation_result is None:
        raise ValueError(
            f"Evaluation result not found in metadata for task in {process_dir}"
        )
    try:
        prompt = prepare_reevaluation_prompt(metadata)
        response_content, cost = await call_llm(
            openai_client, model, prompt=prompt, json_mode=True
        )
        # Process response into an Evaluation structure
        re_evaluation = process_llm_response_into_evaluation(
            response_content, cost, model
        )

        # Update metadata with the re-evaluation and final verdict in-place
        evaluation_result["re_evaluation"] = re_evaluation

        evaluation_result["final_verdict"] = re_evaluation["verdict"]

    except Exception as e:
        print(
            f"An unexpected error occurred during re-evaluation for {process_dir}: {e}"
        )
        raise e
