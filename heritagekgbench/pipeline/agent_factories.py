"""
Agent creation and configuration for Knowledge Graph Construction.

Ported from agentic-kgc ``agent_factories.py``, keeping only
``create_pipeline`` — the factory behind the paper's V2 (agentic baseline)
and V4 (V2 + SHACL repair loop) variants. The CACAO-variant and
ArtKB-variant factories are not part of the release.
"""

import logging

from google.adk.agents import Agent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm

from heritagekgbench.pipeline.agents.coreference.agent import create_coreference_resolution_agent
from heritagekgbench.pipeline.agents.entity_linking.agent import create_entity_linking_agent
from heritagekgbench.pipeline.agents.ner import prompt as ner_prompt
from heritagekgbench.pipeline.agents.ontology import prompt as ontology_prompt
from heritagekgbench.pipeline.agents.ontology.utils import summarize_ontology_for_llm
from heritagekgbench.pipeline.agents.rdf_validator.agent import create_rdf_validator_agent
from heritagekgbench.pipeline.agents.relation_extraction import prompt as re_prompt
from heritagekgbench.pipeline.config import MODEL_ID

logger = logging.getLogger(__name__)


def create_pipeline(
    ontology_path: str,
    model_id: str = MODEL_ID,
    include_entity_linking: bool = False,
) -> SequentialAgent:
    """
    Create a KGC sequential agent pipeline.

    Args:
        ontology_path: Path to the ontology file (OWL/RDF)
        model_id: LLM model identifier
        include_entity_linking: If True, include entity linking step (for production).
            If False, skip entity linking (for benchmark evaluations).

    Returns:
        Configured SequentialAgent instance
    """
    linking_label = "with" if include_entity_linking else "without"
    logger.info(f"Creating pipeline {linking_label} entity linking (model: {model_id})")
    logger.debug(f"Using ontology from: {ontology_path}")

    ontology_summary = summarize_ontology_for_llm(ontology_path)
    logger.debug(f"Ontology summary generated ({len(ontology_summary)} chars)")

    named_entity_recognition_agent = Agent(
        name="ner_agent",
        model=LiteLlm(model=model_id),
        description="Finds named entities in a text.",
        instruction=ner_prompt.NAMED_ENTITY_RECOGNITION_PROMPT + ontology_summary,
        output_key="named_entities",
    )
    logger.debug("Created NER agent")

    sub_agents = [named_entity_recognition_agent]

    # Optionally include entity linking
    if include_entity_linking:
        entity_linking_agent_instance = create_entity_linking_agent(model_id)
        sub_agents.append(entity_linking_agent_instance)
        logger.debug("Created entity linking agent")

    # Coreference resolution
    coreference_agent = create_coreference_resolution_agent(model_id)
    sub_agents.append(coreference_agent)
    logger.debug("Created coreference resolution agent")

    relation_extraction_agent = Agent(
        name="re_agent",
        model=LiteLlm(model=model_id),
        description="Find relation between entities in a text and extracts them.",
        instruction=re_prompt.RELATION_EXTRACTION_PROMPT + ontology_summary,
        output_key="relations",
    )
    sub_agents.append(relation_extraction_agent)
    logger.debug("Created relation extraction agent")

    # Use the linked or non-linked ontology prompt based on entity linking
    ontology_instruction = (
        ontology_prompt.ONTOLOGY_PROMPT
        if include_entity_linking
        else ontology_prompt.ONTOLOGY_PROMPT_NO_LINKED
    )
    ontology_agent = Agent(
        name="ontology_agent",
        model=LiteLlm(model=model_id),
        description="Transforms found relationships between entities into ontology-compliant triples.",
        instruction=ontology_instruction + ontology_summary,
        output_key="ontology_kg",
    )
    sub_agents.append(ontology_agent)
    logger.debug("Created ontology mapping agent")

    # RDF validator
    rdf_validator_agent_instance = create_rdf_validator_agent(model_id)
    sub_agents.append(rdf_validator_agent_instance)
    logger.debug("Created RDF validator agent")

    agent_count = len(sub_agents)
    knowledge_graph_construction_agent = SequentialAgent(
        name="kgc_agent",
        sub_agents=sub_agents,
        description="Executes a sequence of knowledge graph construction tasks.",
    )
    logger.info(f"KGC pipeline created ({agent_count} agents, {linking_label} entity linking)")

    return knowledge_graph_construction_agent
