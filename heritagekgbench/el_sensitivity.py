#!/usr/bin/env python3
"""
el_sensitivity.py - Entity-Linking sensitivity analysis on the CH benchmark.

Recomputes triple-level F1 with `owl:sameAs` triples filtered out of both gold
and prediction, alongside the as-reported F1, for V1 / V2 / V4. 

Outputs:
  - per-text F1 with and without sameAs
  - F1_p (parsed only) and F1_30 (unparseable -> 0) for each setting
  - sameAs counts in gold and pred per text

Ported from agentic-kgc ``scripts/el_sensitivity.py`` with repository-relative
paths; metric logic unchanged.
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

from rdflib import Graph

from heritagekgbench.config import (
    CH_BENCHMARK_CONFIG,
    PREDICTIONS_DIR,
    REPO_ROOT,
    RESULTS_DIR,
)
from heritagekgbench.graph_metrics import (
    _clean_turtle_string,
    calculate_metrics_smart,
    parse_rdf_output,
)
from heritagekgbench.rdf_utils import _strip_markdown_code_blocks

BENCHMARK_JSONL = CH_BENCHMARK_CONFIG["benchmark_jsonl"]
GOLD_BASE = REPO_ROOT  # gold_ttl paths in jsonl are repo-relative ("benchmark/gold/...")

VARIANT_DIRS = {
    "V1_monolithic":   PREDICTIONS_DIR / "single_prompt",
    "V2_baseline":     PREDICTIONS_DIR / "baseline",
    "V4_shacl":        PREDICTIONS_DIR / "shacl",
}


def is_sameas_triple(triple: Dict[str, str]) -> bool:
    """Return True if the triple is an owl:sameAs link.

    parse_rdf_output() resolves owl:sameAs to the suffix "sameAs"; we
    case-fold and tolerate the smart-matching's own normalisation."""
    rel = triple.get("rel", "")
    norm = rel.strip().lower().replace(" ", "").replace("_", "")
    return norm in {"sameas", "owl:sameas"}


def load_pred_turtle(pred_dir: Path, text_id: str) -> str | None:
    f = pred_dir / f"{text_id}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    return _strip_markdown_code_blocks(data.get("output", ""))


def f1_for(gt: List[Dict], pred: List[Dict]) -> float:
    _, _, f1, _, _, _ = calculate_metrics_smart(gt, pred)
    return f1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-csv",
                        default=str(RESULTS_DIR / "el_sensitivity.csv"))
    parser.add_argument("--output-json",
                        default=str(RESULTS_DIR / "el_sensitivity.json"))
    args = parser.parse_args()

    items = [json.loads(l) for l in BENCHMARK_JSONL.read_text(encoding="utf-8").splitlines()
             if l.strip()]

    rows = []
    per_text: Dict[str, list] = {v: [] for v in VARIANT_DIRS}

    for item in items:
        text_id = item["id"]
        gold_path = GOLD_BASE / item["gold_ttl"]
        gold_ttl = gold_path.read_text(encoding="utf-8")
        gt_all = parse_rdf_output(gold_ttl)
        gt_no_sa = [t for t in gt_all if not is_sameas_triple(t)]
        n_gold_sameas = len(gt_all) - len(gt_no_sa)

        for variant, vdir in VARIANT_DIRS.items():
            pred_ttl = load_pred_turtle(vdir, text_id)
            parsed_ok = False
            n_pred = 0
            n_pred_sameas = 0
            f1_full = 0.0
            f1_no_sa = 0.0
            if pred_ttl:
                # "parsed" = rdflib parse succeeds AFTER the same preprocessing
                # the eval pipeline applies (markdown stripping + standard
                # prefix injection). This matches the paper's Table 4 Parsed
                # column. Without _clean_turtle_string, undeclared `ns1:` /
                # `ns3:` prefixes that the LLM emits silently fail.
                cleaned_for_parse = _clean_turtle_string(pred_ttl)
                try:
                    Graph().parse(data=cleaned_for_parse, format="turtle")
                    parsed_ok = True
                except Exception:
                    parsed_ok = False
                pred_all = parse_rdf_output(pred_ttl)
                pred_no_sa = [t for t in pred_all if not is_sameas_triple(t)]
                n_pred = len(pred_all)
                n_pred_sameas = len(pred_all) - len(pred_no_sa)
                if parsed_ok:
                    f1_full = f1_for(gt_all, pred_all)
                    f1_no_sa = f1_for(gt_no_sa, pred_no_sa)

            row = {
                "text_id": text_id,
                "domain": item["domain"],
                "variant": variant,
                "parsed": int(parsed_ok),
                "n_gold": len(gt_all),
                "n_gold_sameas": n_gold_sameas,
                "n_pred": n_pred,
                "n_pred_sameas": n_pred_sameas,
                "f1_full": round(f1_full, 4),
                "f1_no_sameas": round(f1_no_sa, 4),
            }
            rows.append(row)
            per_text[variant].append(row)

    # Aggregate per variant.
    summary: Dict[str, dict] = {}
    for variant, vrows in per_text.items():
        n_total = len(vrows)
        parsed = [r for r in vrows if r["parsed"]]
        n_parsed = len(parsed)
        f1p_full = (sum(r["f1_full"] for r in parsed) / n_parsed) if parsed else 0.0
        f1p_no_sa = (sum(r["f1_no_sameas"] for r in parsed) / n_parsed) if parsed else 0.0
        # F1_30: zero-credit on unparseable.
        f130_full = sum(r["f1_full"] for r in vrows) / n_total
        f130_no_sa = sum(r["f1_no_sameas"] for r in vrows) / n_total

        gold_sameas_total = sum(r["n_gold_sameas"] for r in vrows[:30])
        # gold_sameas is text-property, not variant-property, but per-variant
        # rows are per-text so the slice is fine.

        summary[variant] = {
            "n_total": n_total,
            "n_parsed": n_parsed,
            "f1_p_full":      round(f1p_full, 4),
            "f1_p_no_sameas": round(f1p_no_sa, 4),
            "f1_30_full":      round(f130_full, 4),
            "f1_30_no_sameas": round(f130_no_sa, 4),
            "delta_f1_p":  round(f1p_full - f1p_no_sa, 4),
            "delta_f1_30": round(f130_full - f130_no_sa, 4),
        }

    text_to_gold_sa = {r["text_id"]: r["n_gold_sameas"]
                       for r in rows if r["variant"] == next(iter(VARIANT_DIRS))}
    gold_sameas_total = sum(text_to_gold_sa.values())

    print()
    print("=" * 70)
    print("EL SENSITIVITY: F1 with vs without owl:sameAs in gold/pred")
    print("=" * 70)
    print(f"Gold owl:sameAs across 30 texts: {gold_sameas_total} statements "
          f"(mean {gold_sameas_total/30:.2f}/text)")
    print()
    print(f"{'Variant':<16} {'Parsed':>6}  "
          f"{'F1p full':>9} {'F1p no-SA':>10} {'ΔF1p':>7}  "
          f"{'F1₃₀ full':>9} {'F1₃₀ no-SA':>10} {'ΔF1₃₀':>7}")
    for v, s in summary.items():
        print(f"{v:<16} {s['n_parsed']:>3}/{s['n_total']:<3}  "
              f"{s['f1_p_full']:>9.4f} {s['f1_p_no_sameas']:>10.4f} {s['delta_f1_p']:>+7.4f}  "
              f"{s['f1_30_full']:>9.4f} {s['f1_30_no_sameas']:>10.4f} {s['delta_f1_30']:>+7.4f}")
    print("=" * 70)

    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote per-text rows to {out_csv}")

    out_json = Path(args.output_json)
    out_json.write_text(
        json.dumps({"gold_sameas_total": gold_sameas_total,
                    "summary": summary,
                    "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote summary+rows JSON to {out_json}")


if __name__ == "__main__":
    main()
