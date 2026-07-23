"""
SHACL Validation and Repair Agents for iterative knowledge graph validation.
"""

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from heritagekgbench.pipeline.agents.shacl.prompt import SHACL_REPAIR_PROMPT, SHACL_VALIDATION_PROMPT
from heritagekgbench.pipeline.agents.shacl.tools import validate_with_shacl
from heritagekgbench.pipeline.config import MODEL_ID


def create_shacl_validator_agent(model_id: str = MODEL_ID) -> Agent:
    """
    Create a SHACL validation agent with the specified model.

    Args:
        model_id: LLM model identifier

    Returns:
        Configured Agent instance with SHACL validation tool
    """
    return Agent(
        name="shacl_validator_agent",
        model=LiteLlm(model=model_id),
        description="Validates RDF graphs against SHACL constraints and reports violations.",
        instruction=SHACL_VALIDATION_PROMPT,
        tools=[validate_with_shacl],
        output_key="shacl_validation_result",
    )


def create_shacl_repair_agent(model_id: str = MODEL_ID) -> Agent:
    """
    Create a SHACL repair agent with the specified model.

    Args:
        model_id: LLM model identifier

    Returns:
        Configured Agent instance
    """
    return Agent(
        name="shacl_repair_agent",
        model=LiteLlm(model=model_id),
        description="Repairs RDF graphs by fixing SHACL validation violations.",
        instruction=SHACL_REPAIR_PROMPT,
        output_key="repaired_rdf",
    )
