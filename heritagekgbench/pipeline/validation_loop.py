"""
Iterative SHACL Validation Loop (OntoLogX Adaptation).

This module implements the iterative validation and repair cycle inspired
by the OntoLogX methodology. When the generated RDF graph fails SHACL
validation, it enters a repair loop with a maximum retry limit.
"""

from typing import Dict

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
import logging

logger = logging.getLogger(__name__)

from heritagekgbench.pipeline.agents.shacl.agent import create_shacl_repair_agent, create_shacl_validator_agent
from heritagekgbench.rdf_utils import deduplicate_prefixes

MAX_VALIDATION_ITERATIONS = 3  # Maximum retry count to prevent infinite loops


async def run_with_shacl_validation(
    base_agent: SequentialAgent,
    query: str,
    user_id: str,
    session_id: str,
    session_service: InMemorySessionService,
    run_log: Dict,
    enable_validation: bool = True,
    model_id: str = None,
    ontology_path: str = None,
) -> None:
    """
    Run agent pipeline with iterative SHACL validation loop.

    This function executes the base KGC pipeline, then validates the output
    with SHACL constraints. If validation fails, it enters a repair loop
    where violations are fed back to a repair agent for correction.

    Args:
        base_agent: The main KGC sequential agent
        query: Input text to process
        user_id: User identifier
        session_id: Session identifier
        session_service: Session service for state management
        run_log: Dictionary to populate with results
        enable_validation: If False, skip SHACL validation (backward compatibility)
        model_id: LLM model identifier for SHACL agents (if None, uses default)
        ontology_path: Path to ontology file (used to locate SHACL shapes)
    """
    logger.info(
        f"Running agent with SHACL validation (enabled={enable_validation}, model={model_id})"
    )

    # Step 1: Run the base KGC pipeline
    runner = Runner(agent=base_agent, app_name=user_id, session_service=session_service)

    content = types.Content(role="user", parts=[types.Part(text=query)])
    final_response_text = "Agent did not produce a final response."
    trace = []
    intermediate_states = []

    try:
        logger.info("Executing base KGC pipeline...")
        event_count = 0
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            event_count += 1
            event_type = type(event).__name__
            logger.debug(f"Received event #{event_count}: {event_type}")

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
                logger.info("Base pipeline completed")
                if event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text

        logger.info(f"Base KGC pipeline complete ({event_count} events)")

    except Exception as e:
        logger.error(f"Error during base pipeline: {e}", exc_info=True)
        run_log["input"] = query
        run_log["output"] = f"Error: {str(e)}"
        run_log["logging"] = {"trace": trace, "intermediate_states": intermediate_states}
        return

    # If validation is disabled, return immediately
    if not enable_validation:
        logger.info("SHACL validation disabled, returning base output")
        run_log["input"] = query
        run_log["output"] = final_response_text
        run_log["logging"] = {"trace": trace, "intermediate_states": intermediate_states}
        run_log["validation_iterations"] = 0
        return

    # Step 2: Enter SHACL Validation Loop
    logger.info("Entering SHACL validation loop...")
    current_rdf = final_response_text
    iteration = 0
    validation_passed = False

    validation_history = []

    while iteration < MAX_VALIDATION_ITERATIONS and not validation_passed:
        iteration += 1
        logger.info(f"Validation iteration {iteration}/{MAX_VALIDATION_ITERATIONS}")

        # Create validation agent with correct model_id
        validation_agent = (
            create_shacl_validator_agent(model_id) if model_id else create_shacl_validator_agent()
        )

        # Create new session for validation
        validation_session_id = f"{session_id}_validation_{iteration}"
        validation_state = {"ontology_kg": current_rdf}
        if ontology_path:
            validation_state["_ontology_path"] = ontology_path
        await session_service.create_session(
            app_name=user_id,
            user_id=user_id,
            session_id=validation_session_id,
            state=validation_state,
        )

        validation_runner = Runner(
            agent=validation_agent, app_name=user_id, session_service=session_service
        )

        # Run validation
        validation_result = ""
        try:
            logger.debug("Running SHACL validator agent...")
            validation_content = types.Content(
                role="user", parts=[types.Part(text="Please validate the current RDF graph")]
            )

            async for event in validation_runner.run_async(
                user_id=user_id, session_id=validation_session_id, new_message=validation_content
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        validation_result = event.content.parts[0].text
                        logger.debug(f"Validation result: {validation_result[:200]}...")

        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            validation_result = "ERROR"

        # Check if validation passed
        if "VALID" in validation_result and "INVALID" not in validation_result:
            logger.info("✓ SHACL validation passed!")
            validation_passed = True
            validation_history.append(
                {"iteration": iteration, "status": "PASSED", "result": validation_result}
            )
            break

        # Validation failed - attempt repair
        logger.warning(f"✗ SHACL validation failed at iteration {iteration}")
        validation_history.append(
            {"iteration": iteration, "status": "FAILED", "violations": validation_result}
        )

        if iteration >= MAX_VALIDATION_ITERATIONS:
            logger.warning("Maximum validation iterations reached, stopping loop")
            break

        # Step 3: Run Repair Agent
        logger.info("Running SHACL repair agent...")
        repair_agent = (
            create_shacl_repair_agent(model_id) if model_id else create_shacl_repair_agent()
        )

        repair_session_id = f"{session_id}_repair_{iteration}"
        await session_service.create_session(
            app_name=user_id,
            user_id=user_id,
            session_id=repair_session_id,
            state={"ontology_kg": current_rdf, "shacl_validation_result": validation_result},
        )

        repair_runner = Runner(
            agent=repair_agent, app_name=user_id, session_service=session_service
        )

        # Get repaired RDF
        try:
            logger.debug("Requesting RDF repair...")
            repair_prompt = f"""
The following RDF graph failed SHACL validation.

VIOLATION REPORT:
{validation_result}

ORIGINAL RDF:
{current_rdf}

Please provide the corrected RDF graph that fixes ALL violations.
"""
            repair_content = types.Content(role="user", parts=[types.Part(text=repair_prompt)])

            async for event in repair_runner.run_async(
                user_id=user_id, session_id=repair_session_id, new_message=repair_content
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        current_rdf = event.content.parts[0].text
                        logger.info(f"Received repaired RDF ({len(current_rdf)} chars)")

        except Exception as e:
            logger.error(f"Repair error: {e}")
            break

    # Final output
    run_log["input"] = query
    run_log["output"] = deduplicate_prefixes(current_rdf)
    run_log["logging"] = {"trace": trace, "intermediate_states": intermediate_states}
    run_log["validation_iterations"] = iteration
    run_log["validation_passed"] = validation_passed
    run_log["validation_history"] = validation_history

    if validation_passed:
        logger.info(f"✓ Final output passed SHACL validation after {iteration} iteration(s)")
    else:
        logger.warning(f"⚠ Final output did not pass validation after {iteration} iterations")
