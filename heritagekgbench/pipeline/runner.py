"""
Pipeline runner for the HeritageKGBench baseline systems.

Ported from agentic-kgc ``runner.py``, keeping the three code paths behind
the paper's variants:

- ``single_prompt`` (V1): one LLM call with the ontology summary.
- ``baseline`` (V2): sequential agentic pipeline (NER → entity linking →
  coreference → relation extraction → ontology mapping → RDF validation).
- ``shacl`` (V4): V2 plus an iterative SHACL validate-and-repair loop
  (max 3 iterations).

The Text2KGBench batch runners, the CACAO multi-phase pipeline, the
design-by-contract variants, and the Prometheus/profiling instrumentation
of the source file are not part of the release. The execution logic of the
retained paths is unchanged.
"""

import logging
import uuid as uuid_module
from typing import Dict

from google.adk.agents import Agent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from litellm import acompletion

from heritagekgbench.pipeline.agent_factories import create_pipeline
from heritagekgbench.pipeline.config import MODEL_ID
from heritagekgbench.rdf_utils import deduplicate_prefixes

logger = logging.getLogger(__name__)

VALID_VARIANTS = {"single_prompt", "baseline", "shacl"}


async def call_agent_async(
    query: str, runner: Runner, user_id: str, session_id: str, run_log: Dict
) -> None:
    """
    Execute an agent asynchronously and collect its outputs.

    Args:
        query: Input query/text for the agent
        runner: Configured Runner instance
        user_id: User identifier for session
        session_id: Session identifier
        run_log: Dictionary to populate with execution trace
    """
    logger.info(f"Starting async agent call (query_length: {len(query)})")
    logger.debug(f"User ID: {user_id}, Session ID: {session_id}")

    content = types.Content(role="user", parts=[types.Part(text=query)])
    final_response_text = "Agent did not produce a final response."
    trace = []
    intermediate_states = []

    try:
        event_count = 0
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            event_count += 1
            event_type = type(event).__name__
            logger.debug(f"Received event #{event_count}: {event_type}")

            # Log tool usage
            if hasattr(event, "tool_use") and event.tool_use:
                logger.info(f"Tool used: {event.tool_use.name}")

            trace.append(
                {
                    "author": event.author,
                    "type": event_type,
                    "is_final": event.is_final_response(),
                    "content": str(event.content),
                }
            )

            if hasattr(event, "state"):
                intermediate_states.append(event.state)

            if event.is_final_response():
                logger.info("Final response received from agent")
                if event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text
                elif event.actions and event.actions.escalate:
                    final_response_text = (
                        f"Agent escalated: {event.error_message or 'No specific message.'}"
                    )
                    logger.warning(f"Agent escalated: {event.error_message}")

        logger.info(f"Agent execution complete ({event_count} events processed)")

    except Exception as e:
        logger.error(f"Error during agent execution: {e}", exc_info=True)
        raise

    run_log["input"] = query
    run_log["output"] = deduplicate_prefixes(final_response_text)
    run_log["logging"] = {"trace": trace, "intermediate_states": intermediate_states}


async def run_team_conversation(
    root_agent: Agent, paragraph: str, run_log: Dict, uuid: str
) -> None:
    """
    Run a complete multi-agent conversation for KGC.

    Args:
        root_agent: Root agent or sequential agent to run
        paragraph: Input text to process
        run_log: Dictionary to populate with results
        uuid: Unique identifier for this session
    """
    logger.info("Starting team conversation")
    logger.debug(f"Session UUID: {uuid}")
    logger.debug(f"Input paragraph length: {len(paragraph)} chars")

    session_service = InMemorySessionService()
    await session_service.create_session(app_name=uuid, user_id=uuid, session_id=uuid)

    runner_agent_team = Runner(agent=root_agent, app_name=uuid, session_service=session_service)
    logger.debug(f"Runner created for agent '{root_agent.name}'")

    await call_agent_async(
        query=f"Please construct a knowledge graph about: {paragraph}",
        runner=runner_agent_team,
        user_id=uuid,
        session_id=uuid,
        run_log=run_log,
    )

    logger.info("Team conversation completed")


async def run_team_conversation_with_shacl(
    root_agent: Agent,
    paragraph: str,
    run_log: Dict,
    uuid: str,
    model_id: str = None,
    ontology_path: str = None,
) -> None:
    """
    Run KGC pipeline with iterative SHACL validation loop (OntoLogX adaptation).

    Args:
        root_agent: Root agent or sequential agent to run
        paragraph: Input text to process
        run_log: Dictionary to populate with results
        uuid: Unique identifier for this session
        model_id: LLM model identifier for SHACL agents
        ontology_path: Path to ontology file (used to locate SHACL shapes)

    Returns:
        None (populates run_log with results including validation metadata)
    """
    from heritagekgbench.pipeline.validation_loop import run_with_shacl_validation

    logger.info(f"Starting team conversation WITH SHACL validation loop (model={model_id})")
    logger.debug(f"Session UUID: {uuid}")
    logger.debug(f"Input paragraph length: {len(paragraph)} chars")

    session_service = InMemorySessionService()
    await session_service.create_session(app_name=uuid, user_id=uuid, session_id=uuid)

    # Use the validation loop wrapper if agent is SequentialAgent
    if isinstance(root_agent, SequentialAgent):
        logger.info("Using iterative SHACL validation approach")
        await run_with_shacl_validation(
            base_agent=root_agent,
            query=f"Please construct a knowledge graph about: {paragraph}",
            user_id=uuid,
            session_id=uuid,
            session_service=session_service,
            run_log=run_log,
            enable_validation=True,
            model_id=model_id,
            ontology_path=ontology_path,
        )
    else:
        # If not a SequentialAgent, fall back to standard execution
        # (this shouldn't happen in normal KGC workflow)
        logger.warning(
            f"Agent type {type(root_agent).__name__} is not SequentialAgent, using standard execution"
        )
        runner_agent_team = Runner(
            agent=root_agent, app_name=uuid, session_service=session_service
        )

        await call_agent_async(
            query=f"Please construct a knowledge graph about: {paragraph}",
            runner=runner_agent_team,
            user_id=uuid,
            session_id=uuid,
            run_log=run_log,
        )

    logger.info("Team conversation with SHACL validation completed")


async def process_single_text(
    text: str,
    ontology_path: str,
    model_id: str = MODEL_ID,
    variant: str = "baseline",
) -> Dict:
    """
    Process a single string of text and return the Knowledge Graph result.

    Args:
        text: Input text to process
        ontology_path: Path to ontology file
        model_id: LLM model identifier
        variant: Pipeline variant (single_prompt, baseline, shacl)

    Returns:
        Dictionary with status, input, output, and trace
    """
    if variant not in VALID_VARIANTS:
        return {"error": f"Invalid variant: {variant}", "status": "failed"}

    enable_shacl = "shacl" in variant

    logger.info(f"Processing single text with model: {model_id}, variant: {variant}")
    logger.debug(f"Text length: {len(text)} chars")
    logger.debug(f"Ontology path: {ontology_path}")

    # Initialize the Agent (skip for single_prompt which handles its own setup)
    agent = None
    if variant != "single_prompt":
        try:
            agent = create_pipeline(ontology_path, model_id, include_entity_linking=True)
            logger.info(f"Pipeline agent initialized successfully (variant: {variant})")
        except Exception as e:
            logger.error(f"Failed to create agent: {e}", exc_info=True)
            return {"error": f"Agent creation failed: {str(e)}", "status": "failed"}

    # Prepare Log Container
    run_log = {}
    unique_id = str(uuid_module.uuid4())

    # Run the appropriate pipeline variant
    try:
        if variant == "single_prompt":
            from heritagekgbench.pipeline.agents.ontology.utils import (
                summarize_ontology_for_llm,
            )

            ontology_summary = summarize_ontology_for_llm(ontology_path)
            prompt = (
                f"You are a knowledge graph construction expert. "
                f"Given the following ontology and text, extract all knowledge as "
                f"RDF triples in Turtle format.\n\n"
                f"ONTOLOGY:\n{ontology_summary}\n\n"
                f"TEXT:\n{text}\n\n"
                f"Output ONLY valid RDF/Turtle. Use the ontology classes and "
                f"properties listed above. Include @prefix declarations."
            )
            response = await acompletion(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
            )
            run_log["output"] = response.choices[0].message.content
            logger.info("Single-prompt KG generation completed")

        elif enable_shacl:
            await run_team_conversation_with_shacl(
                agent, text, run_log, unique_id, model_id, ontology_path
            )

        else:
            # Baseline
            await run_team_conversation(
                root_agent=agent, paragraph=text, run_log=run_log, uuid=unique_id
            )

        logger.info("Agent processing completed successfully")

    except Exception as e:
        logger.error(f"Agent processing failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}

    # Extract results
    final_output = run_log.get("output", "")
    logger.info(f"Generated output length: {len(final_output)} chars")

    result = {
        "status": "success",
        "input": text,
        "raw_response": final_output,
        "trace": run_log.get("logging", {}),
    }

    # Add validation metadata when available
    if "validation_passed" in run_log:
        result["validation_passed"] = run_log["validation_passed"]
        result["validation_iterations"] = run_log.get("validation_iterations", 0)

    return result
