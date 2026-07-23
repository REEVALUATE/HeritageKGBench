"""
Fuzzy matching utilities for Knowledge Graph Construction.

This module contains functions for string similarity, stemming,
date normalization, and other text processing utilities.

Ported unchanged from agentic-kgc ``metrics/fuzzy_matching.py``.
"""

from difflib import SequenceMatcher
import functools
import logging
import re
import string
from typing import Set

from dateutil import parser as date_parser
import nltk

logger = logging.getLogger(__name__)


def stem_text(text: str, stemmer) -> str:
    """
    Tokenize and stem text for fuzzy matching.

    Args:
        text: Input text
        stemmer: NLTK stemmer instance

    Returns:
        Stemmed text
    """
    tokens = nltk.word_tokenize(text.lower())
    stems = [stemmer.stem(t) for t in tokens if t.isalnum()]
    return " ".join(stems)


def _check_entity_in_context(
    entity: str, stemmer, stemmed_sentence: str, stemmed_ont_concepts: Set[str]
) -> bool:
    """
    Check if an entity appears in the sentence or ontology concepts.

    Args:
        entity: Entity string to check
        stemmer: NLTK stemmer instance
        stemmed_sentence: Pre-stemmed source sentence
        stemmed_ont_concepts: Pre-stemmed ontology concepts

    Returns:
        True if entity is found in sentence or ontology
    """
    stemmed_entity = stem_text(entity, stemmer)

    # Check if in sentence
    if stemmed_entity in stemmed_sentence:
        return True

    # Check if in ontology concepts
    for concept in stemmed_ont_concepts:
        if stemmed_entity in concept or concept in stemmed_entity:
            return True

    return False


def smart_similarity(a: str, b: str) -> bool:
    """
    Check if two strings are similar using multiple heuristics.

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are considered similar
    """
    if a == b:
        return True
    if a in b or b in a:
        return True

    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return False

    intersection = set_a.intersection(set_b)
    if len(intersection) / min(len(set_a), len(set_b)) > 0.66:
        return True

    return SequenceMatcher(None, a, b).ratio() > 0.85


@functools.lru_cache(maxsize=2048)
def normalize_string(s: str) -> str:
    """
    Normalize a string for comparison (handle dates, punctuation, etc.).

    Memoized with LRU cache for performance when processing large datasets
    with repeated entities/relations.

    Args:
        s: Input string

    Returns:
        Normalized string
    """
    s = str(s).lower().strip()

    # Handle dates
    if any(char.isdigit() for char in s):
        try:
            dt = date_parser.parse(s)
            if re.match(r"^\d{4}$", s):
                return str(dt.year)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # Remove punctuation
    s = s.translate(str.maketrans("", "", string.punctuation))
    return " ".join(s.split())
