"""RDF post-processing utilities.

Shared helpers for cleaning and normalizing Turtle/RDF output produced by
LLM-based KGC systems. Ported unchanged from agentic-kgc ``rdf_utils.py``
(the pipeline-only ``normalize_namespaces`` helper is not part of the
evaluation path and was left out).
"""

import logging
import re
from typing import Dict

from rdflib import Graph

logger = logging.getLogger(__name__)


def deduplicate_prefixes(turtle_string: str) -> str:
    """
    Deduplicate @prefix declarations in a Turtle string.

    Keeps the first declaration for each prefix name. Logs a warning when
    conflicting namespace URIs are found for the same prefix.

    Args:
        turtle_string: Turtle string potentially containing duplicate prefixes

    Returns:
        Turtle string with deduplicated prefix declarations
    """
    lines = turtle_string.split("\n")
    prefix_pattern = re.compile(r"^\s*@prefix\s+(\S+)\s+(<[^>]+>)\s*\.\s*$")
    seen_prefixes: Dict[str, str] = {}
    output_lines = []

    for line in lines:
        match = prefix_pattern.match(line)
        if match:
            prefix_name = match.group(1)
            namespace_uri = match.group(2)

            if prefix_name in seen_prefixes:
                if seen_prefixes[prefix_name] != namespace_uri:
                    logger.warning(
                        f"Conflicting namespace URIs for prefix '{prefix_name}': "
                        f"keeping {seen_prefixes[prefix_name]}, "
                        f"discarding {namespace_uri}"
                    )
                else:
                    logger.debug(f"Removed duplicate @prefix declaration for '{prefix_name}'")
                continue

            seen_prefixes[prefix_name] = namespace_uri

        output_lines.append(line)

    return "\n".join(output_lines)


def _strip_markdown_code_blocks(text: str) -> str:
    """Strip markdown code block fences from a Turtle string."""
    code_block_pattern = r"```(?:turtle)?\s*(.*?)```"
    match = re.search(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.replace("```turtle", "").replace("```", "").strip()


def validate_turtle_syntax(turtle_string: str) -> Dict:
    """
    Parse a Turtle string with rdflib and report syntax errors.

    Args:
        turtle_string: RDF in Turtle format (may include markdown code fences)

    Returns:
        Dict with keys:
        - valid (bool): whether the Turtle parsed successfully
        - triple_count (int): number of triples (0 on failure)
        - error (str): parse error message (empty on success)
    """
    clean = _strip_markdown_code_blocks(turtle_string)

    if not clean:
        return {"valid": False, "triple_count": 0, "error": "Empty input"}

    g = Graph()
    try:
        g.parse(data=clean, format="turtle")
        logger.debug(f"Turtle syntax valid: {len(g)} triples")
        return {"valid": True, "triple_count": len(g), "error": ""}
    except Exception as e:
        error_msg = str(e)
        logger.debug(f"Turtle syntax error: {error_msg}")
        return {"valid": False, "triple_count": 0, "error": error_msg}
