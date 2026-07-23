"""
HeritageKGBench evaluation driver.

Ported from agentic-kgc ``ch_benchmark.py`` (load_benchmark_items,
save_prediction, evaluate_ch_benchmark). The evaluation logic and the score
dict layout are unchanged, so scores computed here are directly comparable to
the shipped ``results/scores/run1_*.json`` files. Two informational keys are
added on top (``n_total``, ``f1_30``) implementing the paper's F1_30 view
(items without a scorable prediction count as F1 = 0 over all 30 texts).

Note on parsing: gold TTL files are parsed through the SAME
``parse_rdf_output()`` as predictions. This drops rdf:type / rdfs:label
statements and resolves URIs to labels, which is why the paper reports less
gold statements rather than rdflib's raw 2,069 (see docs/METRICS.md).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from rdflib import Graph

from heritagekgbench.config import CH_BENCHMARK_CONFIG
from heritagekgbench.graph_level_metrics import (
    entity_recall,
    predicate_coverage,
    type_accuracy,
)
from heritagekgbench.graph_metrics import (
    calculate_metrics_smart,
    get_ontology_meta,
    parse_rdf_output,
)
from heritagekgbench.hallucination_metrics import calculate_hallucination_metrics
from heritagekgbench.rdf_utils import _strip_markdown_code_blocks

logger = logging.getLogger(__name__)


def load_benchmark_items(domain: Optional[str] = None) -> List[Dict]:
    """
    Load benchmark items from benchmark.jsonl.

    Args:
        domain: Optional domain filter (architecture, fashion, olympic, sound).

    Returns:
        List of dicts with keys: id, domain, text, gold_ttl_path.
    """
    benchmark_jsonl = CH_BENCHMARK_CONFIG["benchmark_jsonl"]
    repo_root = benchmark_jsonl.parent.parent  # paths in jsonl are repo-relative

    items = []
    with open(benchmark_jsonl, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if domain and record["domain"] != domain:
                continue

            text_path = repo_root / record["source_text"]
            gold_path = repo_root / record["gold_ttl"]

            if not text_path.exists():
                logger.warning(f"Text file not found: {text_path}")
                continue
            if not gold_path.exists():
                logger.warning(f"Gold TTL not found: {gold_path}")
                continue

            text_content = text_path.read_text(encoding="utf-8").strip()
            items.append({
                "id": record["id"],
                "domain": record["domain"],
                "text": text_content,
                "gold_ttl_path": str(gold_path),
            })

    logger.info(f"Loaded {len(items)} benchmark items" +
                (f" (domain={domain})" if domain else ""))
    return items


def save_prediction(turtle_str: str, text_id: str, output_dir: str) -> Path:
    """
    Save a system prediction as JSON in the format the evaluator expects.

    Args:
        turtle_str: Raw Turtle string from system output.
        text_id: Benchmark text ID (e.g. 'architecture1').
        output_dir: Directory to save the prediction file.

    Returns:
        Path to saved file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    clean_turtle = _strip_markdown_code_blocks(turtle_str)
    result = {"id": text_id, "output": clean_turtle}

    file_path = output_path / f"{text_id}.json"
    file_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.debug(f"Saved prediction for {text_id} ({len(clean_turtle)} chars)")
    return file_path


def evaluate_ch_benchmark(
    pred_dir: str,
    domain: Optional[str] = None,
    debug: bool = False,
) -> Optional[Dict]:
    """
    Evaluate HeritageKGBench predictions.

    Parses both gold TTL files and predicted Turtle through parse_rdf_output()
    to get [{sub, rel, obj}] triples, then uses calculate_metrics_smart()
    and calculate_hallucination_metrics() for consistent evaluation.

    Items whose prediction file is missing or whose output is empty are
    skipped (not scored); the aggregate over the scored items is the paper's
    F1_p view, and ``f1_30`` reports the paper's F1_30 view (skipped items
    counted as 0 over all loaded items).

    Args:
        pred_dir: Directory containing prediction JSON files.
        domain: Optional domain filter.
        debug: Enable debug logging.

    Returns:
        Dict with aggregated metrics (p, r, f1, oc, sh, rh, oh, entity_recall,
        type_f1, predicate_coverage, count, details, n_total, f1_30).
    """
    ontology_path = CH_BENCHMARK_CONFIG["ontology"]
    ontology_graph = Graph()
    try:
        ontology_graph.parse(ontology_path)
        logger.info(f"Loaded ontology from {ontology_path}")
    except Exception as e:
        logger.error(f"Failed to load ontology: {e}")
        ontology_graph = None

    # Extract ontology relations and concepts for hallucination metrics
    ont_relations, ont_concepts = set(), set()
    if ontology_graph:
        ont_relations, ont_concepts = get_ontology_meta(ontology_graph)
    # owl:sameAs is RDF/OWL standard, not a CIDOC-CRM property, but the
    # benchmark uses it for entity links to Wikidata / AAT / ICONCLASS. Whitelist
    # it as a conforming predicate so legitimate links are not flagged in OC/RH.
    ont_relations.add("sameas")

    items = load_benchmark_items(domain)
    pred_path = Path(pred_dir)

    all_metrics = []
    for item in items:
        text_id = item["id"]
        pred_file = pred_path / f"{text_id}.json"

        if not pred_file.exists():
            if debug:
                logger.debug(f"Skipping {text_id}: no prediction file")
            continue

        # Load prediction
        with open(pred_file, encoding="utf-8") as f:
            pred_data = json.load(f)
        pred_turtle = pred_data.get("output", "")
        if not pred_turtle:
            if debug:
                logger.debug(f"{text_id}: empty prediction output")
            continue

        # Parse prediction triples (label-resolved, for Tier 1 metrics)
        pred_triples = parse_rdf_output(pred_turtle, global_ontology=ontology_graph)

        # Parse gold TTL triples (same parser for consistency)
        gold_turtle = Path(item["gold_ttl_path"]).read_text(encoding="utf-8")
        gt_triples = parse_rdf_output(gold_turtle, global_ontology=ontology_graph)

        if not gt_triples:
            logger.warning(f"{text_id}: no triples parsed from gold TTL")
            continue

        # Tier 1: Triple-level metrics
        p, r, f1, _, _, _ = calculate_metrics_smart(gt_triples, pred_triples)
        source_text = item["text"]
        oc, sh, rh, oh = calculate_hallucination_metrics(
            pred_triples, source_text, ont_relations, ont_concepts
        )

        # Tier 2: Graph-level metrics (operate on raw rdflib Graphs)
        gold_g = Graph()
        gold_g.parse(data=gold_turtle, format="turtle")
        pred_g = Graph()
        try:
            clean_pred = _strip_markdown_code_blocks(pred_turtle)
            pred_g.parse(data=clean_pred, format="turtle")
        except Exception:
            pass  # pred_g stays empty if parse fails

        ent_recall = entity_recall(gold_g, pred_g)
        type_acc = type_accuracy(gold_g, pred_g)
        pred_cov = predicate_coverage(gold_g, pred_g)

        if debug:
            logger.info(
                f"{text_id}: P={p:.3f} R={r:.3f} F1={f1:.3f} "
                f"OC={oc:.3f} SH={sh:.3f} RH={rh:.3f} OH={oh:.3f} "
                f"EntR={ent_recall['recall']:.3f} TypeF1={type_acc['f1']:.3f} "
                f"PredCov={pred_cov['coverage']:.3f} "
                f"(gt={len(gt_triples)}, pred={len(pred_triples)})"
            )

        all_metrics.append({
            "id": text_id,
            "domain": item["domain"],
            "p": p, "r": r, "f1": f1,
            "oc": oc, "sh": sh, "rh": rh, "oh": oh,
            "entity_recall": ent_recall["recall"],
            "type_f1": type_acc["f1"],
            "predicate_coverage": pred_cov["coverage"],
            "gt_count": len(gt_triples),
            "pred_count": len(pred_triples),
        })

    if not all_metrics:
        logger.error("No valid predictions found to evaluate")
        return None

    # Aggregate
    n = len(all_metrics)
    avg = lambda key: sum(m[key] for m in all_metrics) / n  # noqa: E731
    result = {
        "p": avg("p"),
        "r": avg("r"),
        "f1": avg("f1"),
        "oc": avg("oc"),
        "sh": avg("sh"),
        "rh": avg("rh"),
        "oh": avg("oh"),
        "entity_recall": avg("entity_recall"),
        "type_f1": avg("type_f1"),
        "predicate_coverage": avg("predicate_coverage"),
        "count": n,
        "details": all_metrics,
        # F1_30 view: unscored items (missing/empty/unparseable prediction)
        # count as 0 over all loaded benchmark items.
        "n_total": len(items),
        "f1_30": sum(m["f1"] for m in all_metrics) / len(items) if items else 0.0,
    }

    logger.info(
        f"HeritageKGBench evaluation: {n}/{len(items)} items scored, "
        f"F1_p={result['f1']:.3f} F1_30={result['f1_30']:.3f} "
        f"EntR={result['entity_recall']:.3f} "
        f"TypeF1={result['type_f1']:.3f} PredCov={result['predicate_coverage']:.3f}"
    )
    return result
