"""DSPy Optimizer for agent prompts."""

from uuid import uuid4
import dspy
from dspy.teleprompt import BootstrapFewShot

from bindu.server.storage.base import Storage
from bindu.utils.logging import get_logger
from bindu.optimization.dataset import generate_golden_dataset

logger = get_logger("bindu.optimization.optimizer")

# Define a simple signature for the agent task
class AgentSignature(dspy.Signature):
    """Refining instructions for an AI agent."""
    question = dspy.InputField()
    answer = dspy.OutputField()

class AgentModule(dspy.Module):
    def __init__(self, base_instruction: str):
        super().__init__()
        self.predictor = dspy.Predict(AgentSignature)
        # We can't easily change the signature's docstring dynamically in DSPy
        # without some metaprogramming, but BootstrapFewShot works by adding examples.
        # The 'base_instruction' is effectively the initial prompt.

    def forward(self, question):
        return self.predictor(question=question)

async def optimize_prompt(
    storage: Storage,
    agent_id: str,
    base_instruction: str,
    metric=None # Optional custom metric
) -> str | None:
    """Run DSPy optimization to generate a new prompt version.

    Args:
        storage: Storage backend.
        agent_id: Agent ID.
        base_instruction: The original instructions for the agent.

    Returns:
        The optimized prompt text (or None if optimization failed/skipped).
    """

    # 1. Generate Golden Dataset
    trainset = await generate_golden_dataset(storage, agent_id)
    if not trainset or len(trainset) < 3: # Need at least a few examples
        logger.info("Not enough data to run optimization.")
        return None

    # 2. Setup DSPy
    # In a real scenario, we'd need a language model configured.
    # Assuming dspy.settings.configure() is called elsewhere or we use defaults.
    # For now, we'll try to use a dummy or require configuration.
    try:
        if not dspy.settings.lm:
             # Fallback or error? Let's log warning.
             logger.warning("DSPy LM not configured. Skipping optimization.")
             return None
    except:
        pass

    # 3. Define Metric (Simple exact match or length check for now)
    # Since we don't have a ground truth for *new* inputs, we are optimizing
    # the few-shot selection for the *existing* high-quality examples.
    def simple_metric(example, pred, trace=None):
        return example.answer == pred.answer

    # 4. Optimize
    # BootstrapFewShot will pick the best examples to include in the prompt
    teleprompter = BootstrapFewShot(metric=simple_metric, max_bootstrapped_demos=3, max_labeled_demos=3)

    # We need a "teacher" module.
    teacher = AgentModule(base_instruction)

    # Compile
    try:
        compiled_program = teleprompter.compile(teacher, trainset=trainset)
    except Exception as e:
        logger.error(f"DSPy optimization failed: {e}")
        return None

    # 5. Extract the optimized prompt
    # In DSPy, the optimization result is a module with demos attached.
    # We need to serialize this into a string prompt that we can inject.

    # This is tricky because DSPy manages the prompt construction internally.
    # However, we can inspect the demos attached to the predictor.
    demos = compiled_program.predictor.demos

    # Construct a prompt string with these demos
    optimized_prompt = base_instruction + "\n\nHere are some examples of high-quality responses:\n\n"

    for i, demo in enumerate(demos):
        optimized_prompt += f"Example {i+1}:\nUser: {demo.question}\nAgent: {demo.answer}\n\n"

    logger.info(f"Generated optimized prompt with {len(demos)} few-shot examples.")

    # 6. Store Candidate
    new_version_id = uuid4()
    # Simple versioning: timestamp based or increment
    from datetime import datetime
    version = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if hasattr(storage, "store_agent_prompt"):
        await storage.store_agent_prompt(
            id=new_version_id,
            agent_id=agent_id,
            version=version,
            prompt_text=optimized_prompt,
            state="candidate"
        )
        return optimized_prompt

    return None
