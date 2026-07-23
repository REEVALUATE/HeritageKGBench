from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from heritagekgbench.pipeline.agents.rdf_validator import prompt
from heritagekgbench.pipeline.agents.rdf_validator.tools import validate_turtle_syntax
from heritagekgbench.pipeline.config import MODEL_ID


def create_rdf_validator_agent(model_id: str = MODEL_ID) -> Agent:
    """
    Create an RDF validator agent with the specified model.

    Args:
        model_id: LLM model identifier

    Returns:
        Configured Agent instance
    """
    return Agent(
        name="rdf_validator_agent",
        model=LiteLlm(model=model_id),
        description="Given triples, this agent will create and validate a knowledge graph in RDF format.",
        instruction=prompt.RDF_VALIDATION_PROMPT,
        output_key="rdf_kg",
        tools=[validate_turtle_syntax],
    )
