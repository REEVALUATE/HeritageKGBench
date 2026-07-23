"""
Graph-level metrics for Knowledge Graph evaluation.

These metrics operate on raw rdflib Graphs (not label-resolved triple dicts)
to capture entity-level, type-level, and predicate-level quality without
requiring structural alignment between gold and predicted graphs.

Ported unchanged from agentic-kgc ``metrics/graph_level_metrics.py``.
"""

import logging
from typing import Dict, List, Set, Tuple

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from heritagekgbench.fuzzy_matching import smart_similarity

logger = logging.getLogger(__name__)

# Predicates to exclude from predicate coverage analysis
_SKIP_PREDICATES = {RDF.type, RDFS.label, OWL.sameAs}


def _extract_labeled_entities(g: Graph) -> Dict[str, URIRef]:
    """Extract entities with labels. Uses rdfs:label if available, falls back to URI local name."""
    entities = {}
    # First pass: entities with rdfs:label
    labeled_uris = set()
    for subj, label in g.subject_objects(RDFS.label):
        if isinstance(subj, URIRef):
            label_str = str(label).strip()
            if label_str:
                entities[label_str] = subj
                labeled_uris.add(subj)

    # Second pass: URIRef subjects without rdfs:label — use local name
    for subj in set(g.subjects()):
        if isinstance(subj, URIRef) and subj not in labeled_uris:
            local = str(subj).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            if local and local not in entities:
                # Convert CamelCase/underscored URIs to readable form
                readable = local.replace("_", " ").replace("-", " ")
                entities[readable] = subj

    return entities


def _extract_type_map(g: Graph) -> Dict[str, Set[str]]:
    """Extract {entity_label: {type_suffix, ...}} from rdf:type triples."""
    type_map: Dict[str, Set[str]] = {}
    # Build label map with fallback to URI local name
    labels = {}
    for subj, label in g.subject_objects(RDFS.label):
        if isinstance(subj, URIRef):
            labels[subj] = str(label).strip()
    for subj in set(g.subjects()):
        if isinstance(subj, URIRef) and subj not in labels:
            local = str(subj).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            labels[subj] = local.replace("_", " ").replace("-", " ")

    for subj, _, obj in g.triples((None, RDF.type, None)):
        if not isinstance(subj, URIRef) or not isinstance(obj, URIRef):
            continue
        label = labels.get(subj)
        if not label:
            continue
        type_str = str(obj).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        type_map.setdefault(label, set()).add(type_str)

    return type_map


def _extract_predicate_suffixes(g: Graph) -> Set[str]:
    """Extract distinct predicate URI suffixes, excluding structural predicates."""
    predicates = set()
    for _, p, _ in g:
        if p in _SKIP_PREDICATES:
            continue
        suffix = str(p).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        predicates.add(suffix)
    return predicates


def entity_recall(gold_graph: Graph, pred_graph: Graph) -> Dict:
    """
    Compute entity-level recall using rdfs:label fuzzy matching.

    Measures whether the same real-world entities are mentioned in both graphs,
    regardless of how they are connected or what graph pattern is used.

    Returns:
        Dict with recall, matched count, and totals.
    """
    gold_entities = _extract_labeled_entities(gold_graph)
    pred_entities = _extract_labeled_entities(pred_graph)

    if not gold_entities:
        return {"recall": 0.0, "matched": 0, "total_gold": 0, "total_pred": len(pred_entities)}

    matched = 0
    matched_labels = []
    pred_labels = list(pred_entities.keys())
    pred_lower_set = {p.lower() for p in pred_labels}

    for gold_label in gold_entities:
        # Prefer exact (case-insensitive) match before fuzzy similarity, for
        # the same reason as in type_accuracy: smart_similarity collisions like
        # 'Berlin' ~ 'Berlin Phonogramm-Archiv' inflate false positives.
        if gold_label in pred_entities or gold_label.lower() in pred_lower_set:
            matched += 1
            matched_labels.append((gold_label, gold_label))
            continue
        for pred_label in pred_labels:
            if smart_similarity(gold_label.lower(), pred_label.lower()):
                matched += 1
                matched_labels.append((gold_label, pred_label))
                break

    recall = matched / len(gold_entities)
    logger.debug(
        f"Entity recall: {matched}/{len(gold_entities)} = {recall:.3f} "
        f"(pred has {len(pred_entities)} entities)"
    )
    return {
        "recall": recall,
        "matched": matched,
        "total_gold": len(gold_entities),
        "total_pred": len(pred_entities),
    }


def type_accuracy(gold_graph: Graph, pred_graph: Graph) -> Dict:
    """
    Compute type assignment accuracy for matched entities.

    For entities that appear in both graphs (by label), checks whether
    they are assigned the same rdf:type classes (e.g., E21_Person, E53_Place).

    Returns:
        Dict with precision, recall, f1, and details.
    """
    gold_types = _extract_type_map(gold_graph)
    pred_types = _extract_type_map(pred_graph)

    if not gold_types:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "matched_entities": 0}

    tp = 0
    fp = 0
    fn = 0
    details = []

    for gold_label, gold_type_set in gold_types.items():
        # Prefer an exact (case-insensitive) label match before falling back to
        # smart_similarity. Fuzzy matching alone causes 'Berlin' to collide with
        # 'Berlin Phonogramm-Archiv', pairing distinct entities and corrupting
        # the type comparison.
        matched_pred_label = None
        if gold_label in pred_types:
            matched_pred_label = gold_label
        else:
            gold_lower = gold_label.lower()
            for pred_label in pred_types:
                if pred_label.lower() == gold_lower:
                    matched_pred_label = pred_label
                    break
        if matched_pred_label is None:
            for pred_label in pred_types:
                if smart_similarity(gold_label.lower(), pred_label.lower()):
                    matched_pred_label = pred_label
                    break

        if matched_pred_label is None:
            fn += len(gold_type_set)
            continue

        pred_type_set = pred_types[matched_pred_label]
        common = gold_type_set & pred_type_set
        tp += len(common)
        fp += len(pred_type_set - gold_type_set)
        fn += len(gold_type_set - pred_type_set)

        if common != gold_type_set or common != pred_type_set:
            details.append({
                "entity": gold_label,
                "gold_types": sorted(gold_type_set),
                "pred_types": sorted(pred_type_set),
                "correct": sorted(common),
            })

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    logger.debug(f"Type accuracy: P={precision:.3f} R={recall:.3f} F1={f1:.3f}")
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def predicate_coverage(gold_graph: Graph, pred_graph: Graph) -> Dict:
    """
    Compute predicate coverage between gold and predicted graphs.

    Measures what fraction of CIDOC-CRM properties used in the gold standard
    are also used in the prediction, based on URI suffix matching.

    Returns:
        Dict with coverage ratio, counts, and lists of matched/missing/extra predicates.
    """
    gold_preds = _extract_predicate_suffixes(gold_graph)
    pred_preds = _extract_predicate_suffixes(pred_graph)

    if not gold_preds:
        return {
            "coverage": 0.0,
            "gold_predicates": 0,
            "pred_predicates": len(pred_preds),
            "matched": [],
            "missing": [],
            "extra": sorted(pred_preds),
        }

    matched = gold_preds & pred_preds
    missing = gold_preds - pred_preds
    extra = pred_preds - gold_preds
    coverage = len(matched) / len(gold_preds)

    logger.debug(
        f"Predicate coverage: {len(matched)}/{len(gold_preds)} = {coverage:.3f} "
        f"(missing: {sorted(missing)[:5]})"
    )
    return {
        "coverage": coverage,
        "gold_predicates": len(gold_preds),
        "pred_predicates": len(pred_preds),
        "matched": sorted(matched),
        "missing": sorted(missing),
        "extra": sorted(extra),
    }
