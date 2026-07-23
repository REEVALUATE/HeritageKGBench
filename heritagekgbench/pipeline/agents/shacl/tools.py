"""
SHACL Validation Tool for Knowledge Graph Validation.

This tool validates RDF graphs against SHACL shapes and provides
detailed violation reports for repair.
"""

from pathlib import Path
from typing import Dict, List, Optional

from google.adk.tools import ToolContext
import logging

logger = logging.getLogger(__name__)
from pyshacl import validate
from rdflib import Graph


def validate_with_shacl(tool_context: ToolContext) -> Dict:
    """
    Validates the generated RDF graph against SHACL shapes.

    This function extracts the RDF output from the previous agent's state,
    validates it against SHACL constraints derived from the ontology,
    and returns a detailed validation report.

    Args:
        tool_context: Context containing the agent state with RDF output

    Returns:
        Dictionary containing:
        - conforms: Boolean indicating if graph is valid
        - violations: List of violation dictionaries with details
        - validation_report: Full SHACL validation report (Turtle format)
        - total_violations: Count of violations
    """
    try:
        # Extract RDF output from previous agent (rdf_agent)
        rdf_output = tool_context.state.get("ontology_kg", "")

        if not rdf_output or rdf_output.strip() == "":
            logger.warning("No RDF output found in tool context state")
            return {
                "conforms": False,
                "violations": [{"message": "No RDF data provided for validation"}],
                "validation_report": "",
                "total_violations": 1,
            }

        # Clean markdown code blocks if present
        rdf_clean = rdf_output.replace("```turtle", "").replace("```", "").strip()

        if not rdf_clean:
            logger.warning("RDF output is empty after cleaning")
            return {
                "conforms": False,
                "violations": [{"message": "Empty RDF data after preprocessing"}],
                "validation_report": "",
                "total_violations": 1,
            }

        logger.info(f"Validating RDF graph ({len(rdf_clean)} chars)")

        # Parse the data graph
        data_graph = Graph()
        try:
            data_graph.parse(data=rdf_clean, format="turtle")
            logger.debug(f"Parsed data graph with {len(data_graph)} triples")
        except Exception as e:
            logger.error(f"Failed to parse RDF data: {e}")
            return {
                "conforms": False,
                "violations": [
                    {"message": f"RDF parsing error: {str(e)}", "severity": "critical"}
                ],
                "validation_report": "",
                "total_violations": 1,
            }

        # Get SHACL shapes from context or generate from ontology
        shacl_shapes = _get_or_generate_shacl_shapes(tool_context)

        if not shacl_shapes:
            logger.warning("No SHACL shapes available, skipping validation")
            return {
                "conforms": True,
                "violations": [],
                "validation_report": "No SHACL shapes defined - validation skipped",
                "total_violations": 0,
            }

        # Parse SHACL shapes graph
        shapes_graph = Graph()
        try:
            shapes_graph.parse(data=shacl_shapes, format="turtle")
            logger.debug(f"Parsed SHACL shapes graph with {len(shapes_graph)} triples")
        except Exception as e:
            logger.error(f"Failed to parse SHACL shapes: {e}")
            return {
                "conforms": False,
                "violations": [
                    {"message": f"SHACL shapes parsing error: {str(e)}", "severity": "critical"}
                ],
                "validation_report": "",
                "total_violations": 1,
            }

        # Run SHACL validation
        logger.info("Running SHACL validation...")
        conforms, results_graph, results_text = validate(
            data_graph,
            shacl_graph=shapes_graph,
            inference="rdfs",  # Use RDFS inference
            abort_on_first=False,  # Get all violations
            meta_shacl=False,
            advanced=True,
            js=False,
        )

        logger.info(f"SHACL validation complete: conforms={conforms}")

        # Parse violation details
        violations = _parse_violations(results_graph) if not conforms else []

        return {
            "conforms": conforms,
            "violations": violations,
            "validation_report": results_text,
            "total_violations": len(violations),
        }

    except Exception as e:
        logger.error(f"SHACL validation error: {e}", exc_info=True)
        return {
            "conforms": False,
            "violations": [
                {"message": f"Validation system error: {str(e)}", "severity": "critical"}
            ],
            "validation_report": "",
            "total_violations": 1,
        }


def _get_or_generate_shacl_shapes(tool_context: ToolContext) -> Optional[str]:
    """
    Retrieves or generates SHACL shapes for validation.

    Priority:
    1. Check if SHACL shapes file exists alongside ontology
    2. Generate shapes from OWL ontology using OWL2SHACL converter
    3. Return basic template as fallback

    Args:
        tool_context: Context with potential ontology path information

    Returns:
        SHACL shapes in Turtle format, or None
    """

    # Try to get ontology path from environment or context
    # This would be set when creating the agent in agents.py
    ontology_path = tool_context.state.get("_ontology_path")

    if ontology_path and Path(ontology_path).exists():
        logger.info(f"Found ontology path: {ontology_path}")

        # Check if pre-generated SHACL file exists
        ontology_file = Path(ontology_path)
        shacl_file = ontology_file.parent / f"{ontology_file.stem}.shacl.ttl"

        if shacl_file.exists():
            logger.info(f"Loading pre-generated SHACL shapes from: {shacl_file}")
            return shacl_file.read_text()

        # Generate SHACL shapes from OWL ontology
        try:
            from heritagekgbench.pipeline.owl_to_shacl import convert_ontology_to_shacl

            logger.info(f"Generating SHACL shapes from ontology: {ontology_path}")
            shapes = convert_ontology_to_shacl(ontology_path)

            # Optionally cache the generated shapes
            shacl_file.write_text(shapes)
            logger.info(f"Cached SHACL shapes to: {shacl_file}")

            return shapes

        except Exception as e:
            logger.warning(f"Failed to generate SHACL from ontology: {e}")
            logger.info("Falling back to basic SHACL shapes")

    # Fallback: basic SHACL shapes template
    basic_shapes = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <http://example.org/shapes#> .

# Basic triple structure validation
ex:TripleShape a sh:NodeShape ;
    sh:targetSubjectsOf rdf:type ;
    sh:property [
        sh:path rdf:type ;
        sh:minCount 1 ;
        sh:message "Every resource must have at least one rdf:type" ;
    ] .

# Ensure all properties have valid objects
ex:PropertyShape a sh:NodeShape ;
    sh:targetSubjectsOf owl:ObjectProperty, owl:DatatypeProperty ;
    sh:property [
        sh:path [ sh:inversePath rdf:type ] ;
        sh:minCount 1 ;
        sh:message "Every property must have a subject" ;
    ] .
"""

    logger.debug("Using basic SHACL shapes template")
    return basic_shapes


def _parse_violations(results_graph: Graph) -> List[Dict]:
    """
    Parses SHACL validation results graph to extract violation details.

    Args:
        results_graph: RDFLib graph containing SHACL validation results

    Returns:
        List of violation dictionaries with structured information
    """

    violations = []

    # Query for all validation results
    query = """
    PREFIX sh: <http://www.w3.org/ns/shacl#>

    SELECT ?result ?focusNode ?resultPath ?value ?message ?severity
    WHERE {
        ?result a sh:ValidationResult ;
                sh:focusNode ?focusNode .
        OPTIONAL { ?result sh:resultPath ?resultPath }
        OPTIONAL { ?result sh:value ?value }
        OPTIONAL { ?result sh:resultMessage ?message }
        OPTIONAL { ?result sh:resultSeverity ?severity }
    }
    """

    try:
        for row in results_graph.query(query):
            violation = {
                "focus_node": str(row.focusNode) if row.focusNode else "unknown",
                "path": str(row.resultPath) if row.resultPath else None,
                "value": str(row.value) if row.value else None,
                "message": str(row.message) if row.message else "Constraint violation",
                "severity": str(row.severity).split("#")[-1] if row.severity else "Violation",
            }
            violations.append(violation)

        logger.info(f"Parsed {len(violations)} violations from results graph")

    except Exception as e:
        logger.error(f"Error parsing violations: {e}")
        # Fallback to simple violation
        violations = [{"message": "Failed to parse detailed violations", "severity": "Error"}]

    return violations
