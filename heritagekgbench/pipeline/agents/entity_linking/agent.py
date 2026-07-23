from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from heritagekgbench.pipeline.agents.entity_linking import prompt
from heritagekgbench.pipeline.agents.entity_linking.tools import search_aat, search_wikidata
from heritagekgbench.pipeline.config import MODEL_ID


def create_entity_linking_agent(model_id: str = MODEL_ID) -> Agent:
    """
    Create an entity linking agent with the specified model.

    Release note: the original experiment code also registered a third tool
    (`search_artkb_batch`) that queried a project-internal GraphDB instance.
    That tool required non-public REEVALUATE infrastructure and is omitted
    here; the public Getty AAT and Wikidata search tools are unchanged.

    Args:
        model_id: LLM model identifier

    Returns:
        Configured Agent instance
    """
    return Agent(
        name="el_agent",
        model=LiteLlm(model=model_id),
        description="Links entities to outside knowledge bases.",
        instruction=prompt.ENTITY_LINKING_PROMPT,
        output_key="linked_entities",
        tools=[
            search_aat,
            search_wikidata,
        ],
    )
