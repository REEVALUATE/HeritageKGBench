import os
from typing import List, Set, Tuple

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS


def get_used_namespace_uris(graph: Graph) -> Set[str]:
    """
    Helper function to get a set of all namespace URIs (as strings)
    that are actually used in the graph's triples.
    """
    used_namespaces = set()

    def extract_ns(term):
        """Helper to extract namespace from a URIRef."""
        if isinstance(term, URIRef):
            try:
                split_point = max(term.rfind("#"), term.rfind("/"))
                if split_point != -1:
                    # The namespace is the part up to and including the split point
                    used_namespaces.add(str(term[: split_point + 1]))
            except Exception:
                pass  # Ignore malformed URIs

    for s, p, o in graph:
        # Check subject, predicate, and object
        extract_ns(s)
        extract_ns(p)
        extract_ns(o)

        # Also check the datatype of literals
        if isinstance(o, Literal) and o.datatype:
            extract_ns(o.datatype)

    return used_namespaces


def get_used_bound_namespaces(graph: Graph) -> List[Tuple[str, URIRef]]:
    """
    Finds all namespaces actually used in the graph and returns them
    in the same format as list(g.namespace_manager.namespaces()).

    This will only return namespaces that are BOTH used AND bound.
    """
    # 1. Get a set of all namespace URIs (as strings) actually in the triples
    used_uris_str = get_used_namespace_uris(graph)

    # 2. Filter the list of all *bound* namespaces
    used_and_bound = []
    for prefix, namespace_uriref in graph.namespace_manager.namespaces():
        # Check if the string version of the bound URI is in our set of used URIs
        if str(namespace_uriref) in used_uris_str:
            used_and_bound.append((prefix, namespace_uriref))

    return used_and_bound


def _parse_ontology_graph(ontology_path: str) -> Graph:
    """
    Parse an ontology file into an rdflib Graph.

    Args:
        ontology_path: Path to the ontology file (OWL, TTL, RDF, JSON-LD).

    Returns:
        Parsed rdflib Graph.

    Raises:
        FileNotFoundError: If the ontology file doesn't exist.
        Exception: If parsing fails.
    """
    if not os.path.exists(ontology_path):
        raise FileNotFoundError(f"Ontology file not found at '{ontology_path}'")

    g = Graph()
    file_extension = os.path.splitext(ontology_path)[1].lower()
    file_format = {
        ".ttl": "turtle",
        ".owl": "xml",
        ".rdf": "xml",
        ".jsonld": "json-ld",
    }.get(file_extension)

    g.parse(ontology_path, format=file_format)
    return g


def extract_ontology_classes(ontology_path: str) -> Set[str]:
    """
    Extract all valid class identifiers and labels from an ontology.

    Returns a set containing multiple forms for each class so that
    any reasonable LLM output can be matched:
    - qnames (e.g., "ns1:Q11424", "cacao:CACAO_0000066")
    - rdfs:labels (e.g., "film", "Person")
    - display format "label (qname)" as produced by summarize_ontology_for_llm()

    Args:
        ontology_path: Path to the ontology file.

    Returns:
        Set of valid class identifier strings.
    """
    g = _parse_ontology_graph(ontology_path)
    valid_classes: Set[str] = set()

    for subject in g.subjects(RDF.type, OWL.Class):
        if not isinstance(subject, URIRef):
            continue

        # Add qname
        try:
            qname = g.qname(subject)
            valid_classes.add(qname)
        except Exception:
            pass

        # Add full URI as fallback
        valid_classes.add(str(subject))

        # Add rdfs:labels
        for label in g.objects(subject=subject, predicate=RDFS.label):
            if isinstance(label, Literal):
                valid_classes.add(str(label))

        # Add display format "label (qname)" for verbatim matches
        labels = list(g.objects(subject=subject, predicate=RDFS.label))
        best_label = None
        for label in labels:
            if isinstance(label, Literal) and label.language == "en":
                best_label = label
                break
        if not best_label:
            for label in labels:
                if isinstance(label, Literal) and not label.language:
                    best_label = label
                    break
        if not best_label and labels:
            best_label = labels[0]

        if best_label:
            try:
                qname = g.qname(subject)
                valid_classes.add(f"{best_label} ({qname})")
            except Exception:
                pass

    return valid_classes


def summarize_ontology_for_llm(ontology_path: str) -> str:
    """
    Parses an ontology file to extract namespaces, classes, properties (using their
    rdfs:label and identifier), and their domains/ranges, then formats this into a
    concise text summary suitable for an LLM context.

    Args:
        ontology_path: The file path to the ontology (e.g., in RDF/XML, Turtle).

    Returns:
        A string containing a summarized version of the ontology.
        Returns an error message if the file cannot be parsed.
    """
    try:
        g = _parse_ontology_graph(ontology_path)
    except FileNotFoundError:
        return f"Error: Ontology file not found at '{ontology_path}'"
    except Exception as e:
        return f"Error parsing ontology file: {e}"

    # --- Helper function to get a formatted name ---
    def get_display_name(subject):
        """
        Gets a display name for a subject, prioritizing the English label.
        If an rdfs:label exists, it returns 'Label (identifier)'.
        Otherwise, it returns just the 'identifier' (qname or URI).
        """
        # Determine the base identifier (qname or full URI as fallback)
        identifier = ""
        if isinstance(subject, URIRef):
            try:
                identifier = g.qname(subject)
            except Exception:
                identifier = str(subject)
        else:
            return str(subject)

        # --- New Label Selection Logic ---
        labels = list(g.objects(subject=subject, predicate=RDFS.label))
        best_label = None

        # 1. Prioritize English ('en') labels
        for label in labels:
            if isinstance(label, Literal) and label.language == "en":
                best_label = label
                break

        # 2. If no English label, look for a label with no language tag
        if not best_label:
            for label in labels:
                if isinstance(label, Literal) and not label.language:
                    best_label = label
                    break

        # 3. If still no suitable label, just grab the first one available
        if not best_label and labels:
            best_label = labels[0]
        # --- End of New Logic ---

        # Format the output string based on whether a label was found
        if best_label:
            return f"{str(best_label)} ({identifier})"
        else:
            return identifier

    # --- 1. Build the Final Summary String ---
    summary_lines = []
    summary_lines.append("<ontology>")

    # --- 2. Extract and Add Namespaces ---
    namespaces = get_used_bound_namespaces(g)
    if namespaces:
        summary_lines.append("\n<namespaces>")
        for prefix, uri in sorted(namespaces):
            summary_lines.append(f"- {prefix}: <{uri}>")
        summary_lines.append("\n</namespaces>")

    else:
        summary_lines.append("\n<namespaces>")
        summary_lines.append("\nNo namespaces found.")
        summary_lines.append("\n</namespaces>")

    # --- 3. Extract Concepts (Classes) ---
    concepts = [
        get_display_name(s) for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)
    ]

    if concepts:
        summary_lines.append("\n<concepts>")
        summary_lines.append("- " + "\n- ".join(sorted(concepts)))
        summary_lines.append("\n</concepts>")
    else:
        summary_lines.append("\n<concepts>")
        summary_lines.append("\nNo concepts (classes) found.")
        summary_lines.append("\n</concepts>")

    # --- 4. Extract Relations (Object and Datatype Properties) ---
    object_properties = g.subjects(RDF.type, OWL.ObjectProperty)
    datatype_properties = g.subjects(RDF.type, OWL.DatatypeProperty)

    relations = []
    all_properties = list(object_properties) + list(datatype_properties)

    for prop in all_properties:
        if isinstance(prop, URIRef):  # Ensure it's not a blank node
            prop_name = get_display_name(prop)

            domains = [
                get_display_name(d) for d in g.objects(prop, RDFS.domain) if isinstance(d, URIRef)
            ]

            ranges = []
            for r in g.objects(prop, RDFS.range):
                if isinstance(r, URIRef):
                    # If the range is a class/concept, get its display name
                    ranges.append(get_display_name(r))
                elif isinstance(r, Literal):
                    # If it's a literal value, show its datatype (e.g., xsd:string)
                    range_qname = g.qname(r.datatype) if r.datatype else "rdfs:Literal"
                    ranges.append(range_qname)
                else:
                    ranges.append("[Anonymous Class/Blank Node]")

            relations.append(
                {
                    "name": prop_name,
                    "domains": domains or ["Not specified"],
                    "ranges": ranges or ["Not specified"],
                }
            )

    # Add relations details
    if relations:
        summary_lines.append("\n<relations>")
        for rel in sorted(relations, key=lambda x: x["name"]):
            domain_str = ", ".join(sorted(rel["domains"]))
            range_str = ", ".join(sorted(rel["ranges"]))
            summary_lines.append(
                f"- Relation '{rel['name']}' connects '{domain_str}' (domain) to '{range_str}' (range)."
            )
        summary_lines.append("\n</relations>")
    else:
        summary_lines.append("\n<relations>")
        summary_lines.append("\nNo relations (properties) found.")
        summary_lines.append("\n</relations>")

    summary_lines.append("\n</ontology>")

    return "\n".join(summary_lines)


# --- Main execution block ---
if __name__ == "__main__":
    ontology_file = "cacao-full.owl"

    print("-" * 50)

    # 2. Run the summarization function on the created file.
    summary = summarize_ontology_for_llm(ontology_file)

    # 3. Print the resulting summary.
    print("Generated LLM Context:")
    print(summary)
