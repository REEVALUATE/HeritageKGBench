#!/usr/bin/env python3
"""
fm_metrics.py — Quantitative metrics for failure modes FM1, FM2, FM5, FM6, FM7
on the Cultural Heritage benchmark.

The paper §5.5 catalogues seven system-output failure modes but only FM3
(entity-linking failure) and FM4 (RDF parse failure) are quantified. The
remaining five (FM1 event flattening, FM2 namespace fabrication, FM5 predicate
substitution, FM6 non-CIDOC vocabulary injection, FM7 temporal handling) are
author observations. This script closes that gap.

Metrics computed per (text, variant):

  FM1 — event_recall:
        Fraction of gold event nodes (CIDOC E5/E7/E8/E9/E10/E11/E12/E13/E14/
        E15/E16/E63/E64/E65/E66/E67/E68/E69/E79/E80/E81/E85/E86/E87)
        present in the prediction's type assertions.
        event_recall = matched_event_types / gold_event_node_count

  FM2 — fabricated_namespace_count:
        Number of distinct URI prefixes used in the prediction that are NOT
        in the allowed set. The allowed set contains structural vocabularies
        (rdf, rdfs, owl, xsd), CACAO and its imports (crm, cacao, foaf, odrl,
        prov, schema), external CH vocabularies (wd, aat, iconclass), the
        benchmark example namespace (ex), and other resolvable vocabularies
        (dc, dcterms, skos). Auto-numbered prefixes (ns1, ns2, ...) are
        always counted as fabricated. Also reports invalid_prefix_count for
        prefixes whose declared URI does not begin with http(s)://.

  FM5 — predicate_substitution_rate:
        For each (subject_label, object_label) pair that appears in both gold
        and prediction, count cases where the predicate differs. Substitution
        is restricted to cases where BOTH predicates are CIDOC properties
        (otherwise it is vocabulary injection, FM6).
        rate = substituted_pairs / matched_pairs

  FM6 — vocab_injection_rate:
        Fraction of predicted triples whose predicate is outside the CACAO
        allowed predicate space. The allowed space is: any URI starting with
        the CIDOC-CRM or CACAO namespace; rdf:type, rdfs:label, owl:sameAs;
        and the specific FOAF/ODRL/PROV/schema terms imported by CACAO
        (loaded from cacao/src/ontology/imports/*_terms.txt at script
        startup). Predicates from non-imported parts of schema, foaf,
        dcterms, etc. count as injection.
        rate = injection_triples / total_pred_triples

  FM7 — temporal_detachment_rate:
        Fraction of E52_Time-Span nodes in prediction that are NOT the object
        of a P4_has_time-span triple (or its inverse P4i). Also reports
        temporal_count for sanity.
        rate = detached_E52 / total_E52

Ported from agentic-kgc ``scripts/fm_metrics.py`` with repository-relative
paths; metric logic unchanged.

Usage:
  python -m heritagekgbench.fm_metrics
  python -m heritagekgbench.fm_metrics --output-json results/fm_metrics.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS

from heritagekgbench.config import (
    CACAO_IMPORTS_DIR,
    CH_BENCHMARK_CONFIG,
    PREDICTIONS_DIR,
    REPO_ROOT,
    RESULTS_DIR,
)
from heritagekgbench.graph_metrics import _clean_turtle_string, parse_rdf_output  # noqa: F401
from heritagekgbench.rdf_utils import _strip_markdown_code_blocks

# Paths
BENCHMARK_JSONL = CH_BENCHMARK_CONFIG["benchmark_jsonl"]
GOLD_BASE = REPO_ROOT  # gold_ttl paths in benchmark.jsonl are repo-relative

VARIANT_DIRS = {
    "V1_monolithic": PREDICTIONS_DIR / "single_prompt",
    "V2_baseline":   PREDICTIONS_DIR / "baseline",
    "V4_shacl":      PREDICTIONS_DIR / "shacl",
}

# CIDOC-CRM namespace
CRM_NS = "http://www.cidoc-crm.org/cidoc-crm/"
CACAO_NS = "http://w3id.org/cacao/"

# CACAO imports a subset of FOAF, ODRL, PROV, and schema.org. Predicates from
# those imported namespaces are part of the allowed predicate space and must
# not be counted as vocabulary injection (FM6) or namespace fabrication (FM2).
# The term lists are vendored from the CACAO repo in ontology/imports/.


def _load_terms(filename: str) -> Set[str]:
    """Load a CACAO imports/*_terms.txt file, excluding comments and blanks."""
    path = CACAO_IMPORTS_DIR / filename
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip().rstrip(".")
        if s and not s.startswith("#"):
            out.add(s)
    return out


CACAO_IMPORTED_PREDICATES: Set[str] = set()
for _f in ("foaf_terms.txt", "odrl_terms.txt", "prov_terms.txt", "schema_terms.txt"):
    CACAO_IMPORTED_PREDICATES |= _load_terms(_f)

# Event classes (subclasses of E2_Temporal_Entity that are events / activities).
# Note: We deliberately exclude E2 itself, E3 (Condition_State), E4 (Period) as
# they are abstract umbrellas; we include the concrete activity/event subclasses.
CIDOC_EVENT_CLASSES = {
    "E5_Event", "E7_Activity", "E8_Acquisition", "E9_Move",
    "E10_Transfer_of_Custody", "E11_Modification", "E12_Production",
    "E13_Attribute_Assignment", "E14_Condition_Assessment",
    "E15_Identifier_Assignment", "E16_Measurement", "E17_Type_Assignment",
    "E63_Beginning_of_Existence", "E64_End_of_Existence",
    "E65_Creation", "E66_Formation", "E67_Birth", "E68_Dissolution",
    "E69_Death", "E79_Part_Addition", "E80_Part_Removal",
    "E81_Transformation", "E83_Type_Creation", "E85_Joining",
    "E86_Leaving", "E87_Curation_Activity",
}

# Allowed namespaces for FM2 (namespace fabrication). The first group is
# structural infrastructure; the second is the CACAO ontology and its imports
# (CIDOC-CRM, FOAF, ODRL, PROV, schema.org); the third is external CH
# vocabularies and the benchmark's example namespace.
ALLOWED_STRUCTURAL_PREFIXES = {"rdf", "rdfs", "owl", "xsd"}
ALLOWED_CACAO_IMPORT_PREFIXES = {"crm", "cidoc", "cidoc-crm", "cacao", "foaf", "odrl", "prov", "schema", "sdo"}
ALLOWED_EXTERNAL_PREFIXES = {"wd", "wikidata", "aat", "getty", "iconclass", "ex", "dc", "dcterms", "skos"}


PREFIX_DECL_RE = re.compile(
    r"@prefix\s+([A-Za-z][A-Za-z0-9_-]*)\s*:\s*<([^>]*)>\s*\.", re.MULTILINE
)


def load_pred_turtle(pred_dir: Path, text_id: str) -> str | None:
    f = pred_dir / f"{text_id}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    return _strip_markdown_code_blocks(data.get("output", ""))


def try_parse(turtle_text: str) -> Graph | None:
    """Return parsed Graph, or None if parsing fails."""
    if not turtle_text:
        return None
    try:
        g = Graph()
        g.parse(data=_clean_turtle_string(turtle_text), format="turtle")
        return g
    except Exception:
        return None


def get_event_node_count(g: Graph) -> Tuple[int, Set[str]]:
    """Count nodes whose rdf:type is a CIDOC event class. Returns (count, labels)."""
    event_nodes = set()
    event_labels = set()
    for s, _, o in g.triples((None, RDF.type, None)):
        if isinstance(o, URIRef):
            local = str(o).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            if local in CIDOC_EVENT_CLASSES:
                event_nodes.add(str(s))
                event_labels.add(local)
    return len(event_nodes), event_labels


def get_used_prefixes(turtle_text: str) -> Dict[str, str]:
    """Return {prefix: uri} for all @prefix declarations in the source text."""
    return {m.group(1): m.group(2) for m in PREFIX_DECL_RE.finditer(turtle_text)}


def is_invalid_namespace_uri(uri: str) -> bool:
    """A namespace URI is invalid if it does not start with http:// or https://."""
    return not (uri.startswith("http://") or uri.startswith("https://"))


def classify_prefix(prefix: str, uri: str) -> str:
    """Classify a prefix into one of: invalid, fabricated, allowed."""
    p = prefix.lower()
    if is_invalid_namespace_uri(uri):
        return "invalid"
    if p in (ALLOWED_STRUCTURAL_PREFIXES | ALLOWED_CACAO_IMPORT_PREFIXES | ALLOWED_EXTERNAL_PREFIXES):
        return "allowed"
    # Auto-numbered prefixes (ns1, ns2, ns3, etc.) emitted by serializers
    # that lost the original prefix mapping. These count as fabricated even
    # when the URI is technically valid, because the prediction has lost the
    # ontology grounding.
    if re.match(r"^ns\d+$", p):
        return "fabricated"
    if CRM_NS in uri or CACAO_NS in uri:
        return "allowed"
    return "fabricated"


def fm1_event_recall(gold_g: Graph, pred_g: Graph | None) -> Dict[str, float]:
    """FM1: fraction of gold event nodes matched in prediction."""
    gold_count, gold_labels = get_event_node_count(gold_g)
    if pred_g is None:
        return {
            "gold_event_count": gold_count,
            "pred_event_count": 0,
            "event_recall": 0.0,
            "gold_event_types": sorted(gold_labels),
            "pred_event_types": [],
        }
    pred_count, pred_labels = get_event_node_count(pred_g)
    # Recall on event types (since exact entity URIs won't match).
    matched = gold_labels & pred_labels
    recall = (len(matched) / len(gold_labels)) if gold_labels else 0.0
    return {
        "gold_event_count": gold_count,
        "pred_event_count": pred_count,
        "event_recall": round(recall, 4),
        "gold_event_types": sorted(gold_labels),
        "pred_event_types": sorted(pred_labels),
    }


def fm2_fabricated_namespaces(pred_turtle: str) -> Dict[str, object]:
    """FM2: count fabricated and invalid namespace prefixes."""
    if not pred_turtle:
        return {
            "fabricated_count": 0,
            "invalid_count": 0,
            "fabricated_prefixes": [],
            "invalid_prefixes": [],
        }
    prefixes = get_used_prefixes(pred_turtle)
    fabricated, invalid = [], []
    for p, u in prefixes.items():
        cls = classify_prefix(p, u)
        if cls == "invalid":
            invalid.append(f"{p}={u}")
        elif cls == "fabricated":
            fabricated.append(f"{p}={u}")
    return {
        "fabricated_count": len(fabricated),
        "invalid_count": len(invalid),
        "fabricated_prefixes": fabricated,
        "invalid_prefixes": invalid,
    }


def get_label(node, g: Graph) -> str:
    """Return a comparable label for an RDF node."""
    if isinstance(node, Literal):
        return str(node).lower().strip()
    if isinstance(node, BNode):
        return ""
    # URIRef: prefer rdfs:label, fall back to URI suffix.
    for lbl in g.objects(node, RDFS.label):
        if isinstance(lbl, Literal):
            return str(lbl).lower().strip()
    s = str(node)
    suffix = s.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return suffix.lower().replace("_", " ").strip()


def predicate_local(p: URIRef) -> str:
    s = str(p)
    return s.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def is_cidoc_predicate(p: URIRef) -> bool:
    s = str(p)
    return s.startswith(CRM_NS) or s.startswith(CACAO_NS)


def cidoc_predicate_set(g: Graph) -> Set[str]:
    """Return the set of local-name CIDOC predicates used as edges in g
    (excluding rdf:type and rdfs:label)."""
    out = set()
    for _, p, _ in g:
        if p == RDF.type or p == RDFS.label:
            continue
        if is_cidoc_predicate(p):
            out.add(predicate_local(p))
    return out


def fm5_predicate_substitution(gold_g: Graph, pred_g: Graph | None) -> Dict[str, object]:
    """FM5 (predicate substitution).

    Two complementary measures:
      (a) pair_substitution_rate: for (subject_label, object_label) pairs that
          appear in BOTH gold and prediction, the fraction where the predicate
          differs (and both predicates are CIDOC). Tight measurement, but
          bounded by entity-matching success and therefore often near-zero on
          low-overlap predictions.

      (b) predicate_set_divergence: CIDOC predicates used by the system that do
          NOT appear in the gold's CIDOC predicate set, divided by the system's
          total CIDOC predicate set. High value = the system picks different
          CIDOC properties than the gold even when it stays within CIDOC.
          Captures the P40-for-P43-style substitution at the predicate-set
          level without requiring pair-level entity match.
    """
    if pred_g is None:
        return {
            "pair_matched": 0, "pair_substituted": 0, "pair_substitution_rate": 0.0,
            "gold_cidoc_predicates": [], "pred_cidoc_predicates": [],
            "pred_divergent_predicates": [], "predicate_set_divergence": 0.0,
            "examples": [],
        }
    gold_pairs: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for s, p, o in gold_g:
        if p == RDF.type or p == RDFS.label or not is_cidoc_predicate(p):
            continue
        sl, ol = get_label(s, gold_g), get_label(o, gold_g)
        if not sl or not ol:
            continue
        gold_pairs[(sl, ol)].append(predicate_local(p))

    pred_pairs: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for s, p, o in pred_g:
        if p == RDF.type or p == RDFS.label or not is_cidoc_predicate(p):
            continue
        sl, ol = get_label(s, pred_g), get_label(o, pred_g)
        if not sl or not ol:
            continue
        pred_pairs[(sl, ol)].append(predicate_local(p))

    matched = 0
    substituted = 0
    examples = []
    for pair, gold_preds in gold_pairs.items():
        if pair not in pred_pairs:
            continue
        matched += 1
        pred_preds_set = set(pred_pairs[pair])
        gold_preds_set = set(gold_preds)
        if pred_preds_set.isdisjoint(gold_preds_set):
            substituted += 1
            if len(examples) < 5:
                examples.append({
                    "subject": pair[0][:60],
                    "object": pair[1][:60],
                    "gold_predicate": sorted(gold_preds_set)[0],
                    "pred_predicate": sorted(pred_preds_set)[0],
                })
    pair_rate = (substituted / matched) if matched else 0.0

    gold_pred_set = cidoc_predicate_set(gold_g)
    pred_pred_set = cidoc_predicate_set(pred_g)
    divergent = pred_pred_set - gold_pred_set
    div_rate = (len(divergent) / len(pred_pred_set)) if pred_pred_set else 0.0

    return {
        "pair_matched": matched,
        "pair_substituted": substituted,
        "pair_substitution_rate": round(pair_rate, 4),
        "gold_cidoc_predicates": sorted(gold_pred_set),
        "pred_cidoc_predicates": sorted(pred_pred_set),
        "pred_divergent_predicates": sorted(divergent),
        "predicate_set_divergence": round(div_rate, 4),
        "examples": examples,
    }


def fm6_vocab_injection(pred_g: Graph | None) -> Dict[str, object]:
    """FM6: fraction of predicted triples whose predicate is outside the CACAO
    allowed predicate space.

    The allowed space is: any CIDOC-CRM or CACAO predicate (matched by URI
    namespace), plus the specific FOAF/ODRL/PROV/schema terms imported by
    CACAO (loaded from cacao/src/ontology/imports/*_terms.txt), plus
    rdf:type, rdfs:label, and owl:sameAs."""
    if pred_g is None:
        return {
            "total_triples": 0,
            "injection_triples": 0,
            "injection_rate": 0.0,
            "injected_predicates": [],
        }
    total = 0
    injected = 0
    injected_preds = set()
    for s, p, o in pred_g:
        total += 1
        if p == RDF.type or p == RDFS.label:
            continue
        ps = str(p)
        if ps.startswith(CRM_NS) or ps.startswith(CACAO_NS):
            continue
        if ps == "http://www.w3.org/2002/07/owl#sameAs":
            continue
        if ps in CACAO_IMPORTED_PREDICATES:
            continue
        injected += 1
        injected_preds.add(predicate_local(p))
    rate = (injected / total) if total else 0.0
    return {
        "total_triples": total,
        "injection_triples": injected,
        "injection_rate": round(rate, 4),
        "injected_predicates": sorted(injected_preds),
    }


P4_PREDICATES = {
    f"{CRM_NS}P4_has_time-span",
    f"{CRM_NS}P4_has_time_span",  # tolerate underscore variant
    f"{CRM_NS}P4i_is_time-span_of",
    f"{CRM_NS}P4i_is_time_span_of",
}


def fm7_temporal_detachment(pred_g: Graph | None) -> Dict[str, object]:
    """FM7: fraction of E52_Time-Span nodes that are NOT attached via P4 / P4i."""
    if pred_g is None:
        return {
            "total_timespan": 0,
            "attached_timespan": 0,
            "detached_timespan": 0,
            "detachment_rate": 0.0,
        }
    timespan_nodes = set()
    for s, _, o in pred_g.triples((None, RDF.type, None)):
        if isinstance(o, URIRef):
            local = str(o).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            # Allow E52_Time-Span with hyphen or underscore.
            if local in {"E52_Time-Span", "E52_Time_Span"}:
                timespan_nodes.add(s)

    attached = set()
    for s, p, o in pred_g:
        if str(p) in P4_PREDICATES:
            # Either S or O is the time-span (P4 vs P4i).
            if o in timespan_nodes:
                attached.add(o)
            if s in timespan_nodes:
                attached.add(s)

    total = len(timespan_nodes)
    n_attached = len(attached)
    detached = total - n_attached
    rate = (detached / total) if total else 0.0
    return {
        "total_timespan": total,
        "attached_timespan": n_attached,
        "detached_timespan": detached,
        "detachment_rate": round(rate, 4),
    }


def aggregate(rows: List[Dict[str, object]], variant: str) -> Dict[str, object]:
    """Aggregate per-text rows for one variant. Treats unparseable as 0 for rate
    metrics; reports parsed-only counts separately."""
    v_rows = [r for r in rows if r["variant"] == variant]
    n_total = len(v_rows)
    parsed = [r for r in v_rows if r["parsed"]]
    n_parsed = len(parsed)

    def mean(field_path: List[str], rows_subset: List[Dict]) -> float:
        vals = []
        for r in rows_subset:
            v = r
            for key in field_path:
                v = v.get(key, 0) if isinstance(v, dict) else 0
            vals.append(float(v) if v is not None else 0.0)
        return sum(vals) / len(vals) if vals else 0.0

    def total(field_path: List[str], rows_subset: List[Dict]) -> int:
        s = 0
        for r in rows_subset:
            v = r
            for key in field_path:
                v = v.get(key, 0) if isinstance(v, dict) else 0
            s += int(v or 0)
        return s

    return {
        "variant": variant,
        "n_total": n_total,
        "n_parsed": n_parsed,

        "FM1_event_recall_parsed_mean":    round(mean(["fm1", "event_recall"], parsed), 4),
        "FM1_event_recall_all_mean":       round(mean(["fm1", "event_recall"], v_rows), 4),
        "FM1_total_gold_events":           total(["fm1", "gold_event_count"], v_rows),
        "FM1_total_pred_events":           total(["fm1", "pred_event_count"], v_rows),

        "FM2_fabricated_namespaces_total": total(["fm2", "fabricated_count"], v_rows),
        "FM2_invalid_namespaces_total":    total(["fm2", "invalid_count"], v_rows),
        "FM2_mean_fabricated_per_text":    round(mean(["fm2", "fabricated_count"], v_rows), 4),

        "FM5_pair_substitution_rate_parsed_mean": round(mean(["fm5", "pair_substitution_rate"], parsed), 4),
        "FM5_total_pair_matched":                  total(["fm5", "pair_matched"], v_rows),
        "FM5_total_pair_substituted":              total(["fm5", "pair_substituted"], v_rows),
        "FM5_predicate_set_divergence_parsed_mean": round(mean(["fm5", "predicate_set_divergence"], parsed), 4),

        "FM6_injection_rate_parsed_mean":  round(mean(["fm6", "injection_rate"], parsed), 4),
        "FM6_total_injection_triples":     total(["fm6", "injection_triples"], v_rows),
        "FM6_total_pred_triples":          total(["fm6", "total_triples"], v_rows),

        "FM7_detachment_rate_parsed_mean": round(mean(["fm7", "detachment_rate"], parsed), 4),
        "FM7_total_timespan_nodes":        total(["fm7", "total_timespan"], v_rows),
        "FM7_total_detached_timespan":     total(["fm7", "detached_timespan"], v_rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-json",
                    default=str(RESULTS_DIR / "fm_metrics.json"))
    args = ap.parse_args()

    items = [
        json.loads(l)
        for l in BENCHMARK_JSONL.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]

    rows: List[Dict[str, object]] = []

    for item in items:
        text_id = item["id"]
        domain = item["domain"]
        gold_path = GOLD_BASE / item["gold_ttl"]
        gold_ttl = gold_path.read_text(encoding="utf-8")
        gold_g = Graph()
        gold_g.parse(data=gold_ttl, format="turtle")

        for variant, vdir in VARIANT_DIRS.items():
            pred_ttl = load_pred_turtle(vdir, text_id)
            pred_g = try_parse(pred_ttl) if pred_ttl else None
            parsed = pred_g is not None

            row = {
                "text_id": text_id,
                "domain": domain,
                "variant": variant,
                "parsed": parsed,
                "fm1": fm1_event_recall(gold_g, pred_g),
                "fm2": fm2_fabricated_namespaces(pred_ttl or ""),
                "fm5": fm5_predicate_substitution(gold_g, pred_g),
                "fm6": fm6_vocab_injection(pred_g),
                "fm7": fm7_temporal_detachment(pred_g),
            }
            rows.append(row)

    summary = {v: aggregate(rows, v) for v in VARIANT_DIRS}

    output = {
        "summary": summary,
        "per_text": rows,
    }

    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

    # Print a compact summary to stdout.
    print(f"Wrote {out_path}")
    print()
    for variant, s in summary.items():
        print(f"=== {variant} (parsed {s['n_parsed']}/{s['n_total']}) ===")
        print(f"  FM1 event recall (parsed):  {s['FM1_event_recall_parsed_mean']:.3f}  "
              f"(pred events: {s['FM1_total_pred_events']} / gold {s['FM1_total_gold_events']})")
        print(f"  FM2 fabricated NS / text:   {s['FM2_mean_fabricated_per_text']:.2f}  "
              f"(total {s['FM2_fabricated_namespaces_total']}, invalid {s['FM2_invalid_namespaces_total']})")
        print(f"  FM5 pair substitution rate: {s['FM5_pair_substitution_rate_parsed_mean']:.3f}  "
              f"(substituted {s['FM5_total_pair_substituted']} / matched {s['FM5_total_pair_matched']} pairs)")
        print(f"  FM5 predicate-set diverg.:  {s['FM5_predicate_set_divergence_parsed_mean']:.3f}  "
              f"(divergent CIDOC predicates / pred-side CIDOC predicates)")
        print(f"  FM6 vocab injection rate:   {s['FM6_injection_rate_parsed_mean']:.3f}  "
              f"(injected {s['FM6_total_injection_triples']} / total {s['FM6_total_pred_triples']})")
        print(f"  FM7 temporal detachment:    {s['FM7_detachment_rate_parsed_mean']:.3f}  "
              f"(detached {s['FM7_total_detached_timespan']} / total {s['FM7_total_timespan_nodes']})")
        print()


if __name__ == "__main__":
    main()
