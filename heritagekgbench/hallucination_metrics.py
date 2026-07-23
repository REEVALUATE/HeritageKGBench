"""
Hallucination metrics for Knowledge Graph Construction (Tier 3).

This module contains functions for calculating hallucination metrics:
- OC (Ontology Conformance): % of relations that exist in ontology
- SH (Subject Hallucination): % of subjects not in sentence or ontology
- RH (Relation Hallucination): % of relations not in ontology
- OH (Object Hallucination): % of objects not in sentence or ontology

Ported from agentic-kgc ``metrics/hallucination_metrics.py``; the TTL-based
SimpleCache was replaced by a plain module-level dict (same behaviour within
one evaluation run).
"""

import logging
from typing import Dict, List, Set, Tuple

from nltk.stem.snowball import SnowballStemmer

from heritagekgbench.fuzzy_matching import _check_entity_in_context, stem_text

logger = logging.getLogger(__name__)

# In-process cache of stemmed ontology concept sets (keyed by concept-set hash).
_stemmed_concepts_cache: Dict[str, Set[str]] = {}


def calculate_hallucination_metrics(
    pred_triples: List[Dict], source_sentence: str, ont_relations: Set[str], ont_concepts: Set[str]
) -> Tuple[float, float, float, float]:
    """
    Calculate hallucination metrics for predicted triples.

    Metrics:
    - OC (Ontology Conformance): % of relations that exist in ontology
    - SH (Subject Hallucination): % of subjects not in sentence or ontology
    - RH (Relation Hallucination): % of relations not in ontology
    - OH (Object Hallucination): % of objects not in sentence or ontology

    Args:
        pred_triples: List of predicted triples
        source_sentence: Original source text
        ont_relations: Set of valid ontology relations
        ont_concepts: Set of valid ontology concepts

    Returns:
        Tuple of (oc_score, sh_score, rh_score, oh_score)
    """
    if not pred_triples:
        logger.debug("No predicted triples, returning zero hallucination metrics")
        return 0.0, 0.0, 0.0, 0.0

    stemmer = SnowballStemmer("english")
    stemmed_sentence = stem_text(source_sentence, stemmer)

    # Cache stemmed concepts to avoid repeated stemming (performance optimization)
    concepts_key = f"stemmed_concepts_{hash(frozenset(ont_concepts))}"
    stemmed_ont_concepts = _stemmed_concepts_cache.get(concepts_key)
    if stemmed_ont_concepts is None:
        stemmed_ont_concepts = {stem_text(c, stemmer) for c in ont_concepts}
        _stemmed_concepts_cache[concepts_key] = stemmed_ont_concepts

    total = len(pred_triples)
    conforming_rels = 0
    sh_count = 0
    oh_count = 0
    rh_count = 0

    for t in pred_triples:
        sub = t["sub"].lower().strip()
        rel = t["rel"].lower().strip()
        obj = t["obj"].lower().strip()

        # Check relation hallucination
        if rel in ont_relations:
            conforming_rels += 1
        else:
            rh_count += 1

        # Check subject hallucination
        if not _check_entity_in_context(sub, stemmer, stemmed_sentence, stemmed_ont_concepts):
            sh_count += 1

        # Check object hallucination
        if not _check_entity_in_context(obj, stemmer, stemmed_sentence, stemmed_ont_concepts):
            oh_count += 1

    oc_score = conforming_rels / total if total > 0 else 0.0
    rh_score = rh_count / total if total > 0 else 0.0
    sh_score = sh_count / total if total > 0 else 0.0
    oh_score = oh_count / total if total > 0 else 0.0

    logger.debug(
        f"Hallucination metrics - OC: {oc_score:.3f}, SH: {sh_score:.3f}, "
        f"RH: {rh_score:.3f}, OH: {oh_score:.3f}"
    )
    return oc_score, sh_score, rh_score, oh_score
