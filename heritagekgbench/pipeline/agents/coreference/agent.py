from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from heritagekgbench.pipeline.agents.coreference import prompt
from heritagekgbench.pipeline.config import MODEL_ID


def create_coreference_resolution_agent(model_id: str = MODEL_ID) -> Agent:
    """
    Create a coreference resolution agent with the specified model.

    Args:
        model_id: LLM model identifier

    Returns:
        Configured Agent instance
    """
    return Agent(
        name="cr_agent",
        model=LiteLlm(model=model_id),
        description="Finds coreferrenced entities in a text.",
        instruction=prompt.COREFERENCE_RESOLUTION_PROMPT,
        output_key="coreferences",
    )
