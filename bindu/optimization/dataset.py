"""Dataset generation for DSPy optimization."""

from typing import Any
from uuid import UUID
import dspy

from bindu.server.storage.base import Storage
from bindu.utils.logging import get_logger

logger = get_logger("bindu.optimization.dataset")

async def generate_golden_dataset(
    storage: Storage,
    agent_id: str, # Currently unused in storage query but useful for future filtering
    min_rating: int = 4
) -> list[dspy.Example]:
    """Generate a golden dataset from task feedback.

    Args:
        storage: The storage backend.
        agent_id: The ID of the agent to generate dataset for.
        min_rating: Minimum rating (1-5) to include in the dataset.

    Returns:
        List of dspy.Example objects (input, output).
    """
    if not hasattr(storage, "get_task_feedback") or not hasattr(storage, "load_task"):
        logger.warning("Storage does not support feedback retrieval.")
        return []

    # 1. Fetch all feedback (Note: storage.get_task_feedback is per task, we need a bulk way or iterate)
    # The current storage interface is limited. We might need to extend it to list all feedback.
    # For now, let's assume we can list tasks and check feedback for them.
    # This is inefficient but functional for MVP.

    tasks = await storage.list_tasks(length=100) # Limit to 100 recent tasks for now
    dataset = []

    for task in tasks:
        # Check feedback
        feedback_list = await storage.get_task_feedback(task["id"])
        if not feedback_list:
            continue

        # Check if any feedback meets criteria
        best_feedback = max(feedback_list, key=lambda f: f.get("rating", 0))
        if best_feedback.get("rating", 0) < min_rating:
            continue

        # Construct Example
        # Input: User's last message or full history?
        # Output: Agent's response (from artifacts or history)

        history = task.get("history", [])
        if not history:
            continue

        # Simple heuristic: Last user message is input, last agent message is output
        # A more robust approach would reconstruction conversation

        user_input = None
        agent_output = None

        # Walk backwards
        for msg in reversed(history):
            if msg["role"] == "user" and not user_input:
                # Extract text
                parts = msg.get("parts", [])
                text_parts = [p["text"] for p in parts if p["kind"] == "text"]
                if text_parts:
                    user_input = "\n".join(text_parts)
            elif msg["role"] == "agent" and not agent_output:
                parts = msg.get("parts", [])
                text_parts = [p["text"] for p in parts if p["kind"] == "text"]
                if text_parts:
                    agent_output = "\n".join(text_parts)

            if user_input and agent_output:
                break

        if user_input and agent_output:
            dataset.append(dspy.Example(question=user_input, answer=agent_output).with_inputs("question"))

    logger.info(f"Generated golden dataset with {len(dataset)} examples for agent {agent_id}")
    return dataset
