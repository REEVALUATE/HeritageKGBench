"""
Graph metrics for Knowledge Graph Construction (Tier 1).

Turtle parsing/normalization and triple-level precision/recall/F1 with fuzzy
matching. Ported from agentic-kgc ``metrics/graph_metrics.py``; the
Text2KGBench-specific entry points (topic evaluation, per-topic ontology
loading) were removed, everything on the CH evaluation path is unchanged.
"""

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from rdflib import BNode, Graph
from rdflib.namespace import RDF, RDFS

from heritagekgbench.fuzzy_matching import normalize_string, smart_similarity
from heritagekgbench.rdf_utils import deduplicate_prefixes

logger = logging.getLogger(__name__)


def get_ontology_meta(graph: Graph) -> Tuple[Set[str], Set[str]]:
    """
    Extract relations and concepts from an RDF ontology graph.

    Args:
        graph: RDFLib Graph object

    Returns:
        Tuple of (relations set, concepts set)
    """
    from rdflib import URIRef

    logger.debug("Extracting ontology metadata")
    relations = set()
    concepts = set()

    # Extract concepts from rdfs:label
    for _, obj in graph.subject_objects(RDFS.label):
        concepts.add(str(obj).lower().strip())

    # Extract relations (properties)
    for s, p, o in graph:
        if o in (
            RDF.Property,
            URIRef("http://www.w3.org/2002/07/owl#ObjectProperty"),
            URIRef("http://www.w3.org/2002/07/owl#DatatypeProperty"),
        ):
            for _, label in graph.subject_objects(RDFS.label):
                if _ == s:
                    relations.add(str(label).lower().strip())

    logger.info(f"Extracted {len(relations)} relations and {len(concepts)} concepts from ontology")
    return relations, concepts


def _normalize_triple_list(
    triples: List[Dict], relevant_relations: Optional[Set[str]] = None
) -> List[Dict]:
    """
    Normalize triples and optionally filter by relevant relations.

    Args:
        triples: List of triple dictionaries
        relevant_relations: Optional set of relations to filter by

    Returns:
        List of normalized triple items with matched flag
    """
    normalized = []
    for t in triples:
        norm_rel = normalize_string(t["rel"])

        # Filter by relevant relations if provided
        if relevant_relations is not None:
            if norm_rel not in relevant_relations:
                continue
            # Skip Wikidata property IDs like "p123"
            if re.match(r"^p\d+$", norm_rel):
                continue

        normalized.append(
            {
                "sub": normalize_string(t["sub"]),
                "rel": norm_rel,
                "obj": normalize_string(t["obj"]),
                "raw": t,
                "matched": False,
            }
        )
    return normalized


def _find_matching_triples(
    pred_items: List[Dict], gt_items: List[Dict]
) -> Set[Tuple[str, str, str]]:
    """
    Find matching triples between predictions and ground truth using fuzzy matching.

    Optimized version that groups triples by relation to reduce comparisons
    from O(n×m) to O(n×m/k) where k is the average number of unique relations.

    Args:
        pred_items: Normalized predicted triples
        gt_items: Normalized ground truth triples

    Returns:
        Set of matched triple tuples
    """
    # Group ground truth items by relation for faster lookup
    gt_by_relation = {}
    for g in gt_items:
        rel = g["rel"]
        if rel not in gt_by_relation:
            gt_by_relation[rel] = []
        gt_by_relation[rel].append(g)

    matched_tuples = set()
    for p in pred_items:
        # Only compare with ground truth items that have the same relation
        candidates = gt_by_relation.get(p["rel"], [])
        for g in candidates:
            if g["matched"]:
                continue
            # Relation already matches, only check subject and object
            sub_match = smart_similarity(p["sub"], g["sub"])
            obj_match = smart_similarity(p["obj"], g["obj"])
            if sub_match and obj_match:
                g["matched"] = True
                p["matched"] = True
                matched_tuples.add((p["sub"], p["rel"], p["obj"]))
                break
    return matched_tuples


def calculate_metrics_smart(ground_truth_list: List[Dict], predicted_list: List[Dict]):
    """
    Calculate precision, recall, F1 using smart fuzzy matching.

    This function uses semantic similarity matching rather than exact string matching.

    Args:
        ground_truth_list: List of ground truth triples
        predicted_list: List of predicted triples

    Returns:
        Tuple of (precision, recall, f1, extras, missed, matched_tuples)
    """
    logger.debug(
        f"Calculating smart metrics for {len(ground_truth_list)} GT and "
        f"{len(predicted_list)} predicted triples"
    )

    relevant_relations = set(normalize_string(t["rel"]) for t in ground_truth_list)

    gt_items = _normalize_triple_list(ground_truth_list)
    pred_items = _normalize_triple_list(predicted_list, relevant_relations)

    matched_tuples = _find_matching_triples(pred_items, gt_items)

    tp = len(matched_tuples)
    extras_list = [(p["sub"], p["rel"], p["obj"]) for p in pred_items if not p["matched"]]
    fp = len(extras_list)
    missed_list = [(g["sub"], g["rel"], g["obj"]) for g in gt_items if not g["matched"]]
    fn = len(missed_list)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    logger.info(
        f"Metrics - Precision: {precision:.3f}, Recall: {recall:.3f}, F1: {f1:.3f} "
        f"(TP: {tp}, FP: {fp}, FN: {fn})"
    )
    return precision, recall, f1, set(extras_list), set(missed_list), matched_tuples


def calculate_metrics(ground_truth_list: List[Dict], predicted_list: List[Dict]):
    """
    Calculate precision, recall, F1 using exact matching.

    Args:
        ground_truth_list: List of ground truth triples
        predicted_list: List of predicted triples

    Returns:
        Tuple of (precision, recall, f1)
    """
    logger.debug(
        f"Calculating exact metrics for {len(ground_truth_list)} GT and "
        f"{len(predicted_list)} predicted triples"
    )

    gt_set = set()
    for t in ground_truth_list:
        gt_set.add(
            (normalize_string(t["sub"]), normalize_string(t["rel"]), normalize_string(t["obj"]))
        )

    pred_set = set()
    for t in predicted_list:
        pred_set.add(
            (normalize_string(t["sub"]), normalize_string(t["rel"]), normalize_string(t["obj"]))
        )

    intersection = gt_set.intersection(pred_set)
    tp = len(intersection)
    fp = len(pred_set) - tp
    fn = len(gt_set) - tp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    logger.info(f"Exact metrics - Precision: {precision:.3f}, Recall: {recall:.3f}, F1: {f1:.3f}")
    return precision, recall, f1


def _clean_turtle_string(turtle_string: str) -> str:
    """
    Extract and clean Turtle/RDF string from markdown code blocks.

    Args:
        turtle_string: Raw Turtle string, possibly with markdown formatting

    Returns:
        Cleaned Turtle string with prefixes added if needed
    """
    # Extract from code blocks if present
    code_block_pattern = r"```(?:turtle)?\s*(.*?)```"
    match = re.search(code_block_pattern, turtle_string, re.DOTALL | re.IGNORECASE)
    if match:
        clean_turtle = match.group(1).strip()
        logger.debug("Extracted Turtle from code block")
    else:
        clean_turtle = turtle_string.replace("```turtle", "").replace("```", "").strip()

    # Add standard prefixes if missing
    prefix_header = """
    @prefix ns1: <http://example.org/ns1/> .
    @prefix ns2: <http://example.org/ns2/> .
    @prefix ns3: <http://example.org/ns3/> .
    @prefix wd: <http://www.wikidata.org/entity/> .
    @prefix wdt: <http://www.wikidata.org/prop/direct/> .
    """
    if "@prefix" not in clean_turtle and "ns" in clean_turtle:
        clean_turtle = prefix_header + clean_turtle
        logger.debug("Added standard prefixes to Turtle")

    # Deduplicate prefix declarations
    clean_turtle = deduplicate_prefixes(clean_turtle)

    return clean_turtle


def _build_label_mappings(
    graph: Graph, global_ontology: Optional[Graph]
) -> Tuple[Dict, Dict[str, str]]:
    """
    Build label mappings from local graph and global ontology.

    Multi-language ontologies (e.g. cacao-full.owl) carry rdfs:label triples in
    several languages per resource. We pick English deterministically: an @en
    label always wins over any other tag, and an untagged literal is used as a
    fallback only when no @en label exists.

    Args:
        graph: Local RDF graph
        global_ontology: Optional global ontology graph

    Returns:
        Tuple of (local_labels dict, global_id_to_label dict)
    """

    def _add(g: Graph, target: Dict) -> None:
        for sub, obj in g.subject_objects(RDFS.label):
            lang = getattr(obj, "language", None)
            if lang is None:
                target.setdefault(sub, str(obj))
            elif lang == "en":
                target[sub] = str(obj)

    local_labels: Dict = {}
    _add(graph, local_labels)

    global_id_to_label: Dict[str, str] = {}
    if global_ontology:
        _add(global_ontology, local_labels)
        for sub, obj in global_ontology.subject_objects(RDFS.label):
            lang = getattr(obj, "language", None)
            if lang is not None and lang != "en":
                continue
            uri_str = str(sub)
            if "#" in uri_str:
                suffix = uri_str.split("#")[-1]
            elif "/" in uri_str:
                suffix = uri_str.split("/")[-1]
            elif ":" in uri_str:
                suffix = uri_str.split(":")[-1]
            else:
                continue
            if lang == "en" or suffix not in global_id_to_label:
                global_id_to_label[suffix] = str(obj)

    return local_labels, global_id_to_label


def _resolve_node(node, local_labels: Dict, global_id_to_label: Dict[str, str]) -> str:
    """
    Resolve RDF node to human-readable label.

    Args:
        node: RDF node to resolve
        local_labels: Dictionary of local label mappings
        global_id_to_label: Dictionary of global ID to label mappings

    Returns:
        Human-readable label string
    """
    if node in local_labels:
        return local_labels[node]

    s_node = str(node)
    if "http" in s_node or "://" in s_node:
        possible_id = s_node.replace(">", "").split("/")[-1].split("#")[-1]
    else:
        possible_id = s_node.split(":")[-1]

    if possible_id in global_id_to_label:
        return global_id_to_label[possible_id]

    return possible_id.replace("_", " ").strip()


def parse_rdf_output(
    turtle_string: str, global_ontology: Optional[Graph] = None
) -> List[Dict[str, str]]:
    """
    Parse Turtle/RDF output into structured triples.

    Args:
        turtle_string: RDF in Turtle format
        global_ontology: Optional ontology graph for label resolution

    Returns:
        List of triple dictionaries with keys: sub, rel, obj
    """
    if not turtle_string:
        logger.debug("Empty turtle string provided")
        return []

    clean_turtle = _clean_turtle_string(turtle_string)

    g = Graph()
    try:
        g.parse(data=clean_turtle, format="turtle")
        logger.debug(f"Successfully parsed RDF graph with {len(g)} triples")
    except Exception as e:
        logger.error(f"Failed to parse RDF: {e}")
        return []

    local_labels, global_id_to_label = _build_label_mappings(g, global_ontology)

    # Build stable labels for blank nodes from their properties
    # so that the same blank node parsed twice gets the same label
    bnode_labels: Dict = {}
    for bnode in set(s for s in g.subjects() if isinstance(s, BNode)):
        if bnode in local_labels:
            bnode_labels[bnode] = local_labels[bnode]
            continue
        # Build a label from rdf:type + property values
        parts = []
        for _, p_val, o_val in g.triples((bnode, None, None)):
            if p_val == RDF.type:
                type_str = str(o_val).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                parts.insert(0, type_str)
            elif p_val == RDFS.label:
                continue  # already in local_labels
            else:
                pred_str = str(p_val).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                obj_str = str(o_val) if not isinstance(o_val, BNode) else "_"
                if "http" in obj_str:
                    obj_str = obj_str.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                parts.append(f"{pred_str}={obj_str}")
        if parts:
            bnode_labels[bnode] = " ".join(sorted(parts))
        else:
            bnode_labels[bnode] = "_blank"
    local_labels.update(bnode_labels)

    final_triples = []
    for s, p, o in g:
        if p == RDFS.label or p == RDF.type:
            continue
        sub_txt = _resolve_node(s, local_labels, global_id_to_label)
        pred_txt = _resolve_node(p, local_labels, global_id_to_label)
        obj_txt = _resolve_node(o, local_labels, global_id_to_label)
        final_triples.append({"sub": sub_txt, "rel": pred_txt, "obj": obj_txt})

    logger.info(f"Parsed {len(final_triples)} semantic triples from RDF")
    return final_triples
