#!/usr/bin/env python3
"""Rebuild the paper's HeritageKGBench tables from the shipped result JSONs.

  Table 4 (tab:ch-headline)       -> table4_ch_headline.csv
  Table 5 (tab:fm-system-metrics) -> table5_fm_system_metrics.csv
  verification.csv                -> each cell vs. the paper's printed value

    heritagekgbench paper-tables
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List

from heritagekgbench.config import PREDICTIONS_DIR, RESULTS_DIR

SCORES_DIR = RESULTS_DIR / "scores"
FM_METRICS_JSON = RESULTS_DIR / "fm_metrics.json"
EL_SENSITIVITY_JSON = RESULTS_DIR / "el_sensitivity.json"
DEFAULT_OUT_DIR = RESULTS_DIR / "paper_tables"

# Paper variant label -> (score file, fm_metrics key, predictions subdir).
VARIANTS = {
    "V1": ("run1_single_prompt.json", "V1_monolithic", "single_prompt"),
    "V2": ("run1_baseline.json", "V2_baseline", "baseline"),
    "V4": ("run1_shacl.json", "V4_shacl", "shacl"),
}
GOLD_SCORE_FILE = "gold_standard.json"
N_TEXTS = 30

# ── Paper's printed values (reference only, for the diff column) ──────────────
# Table 4 (tab:ch-headline): F1_p, F1_30, OC, RH, ER, TF1, PC, Parsed.
PAPER_CH = {
    "Gold": (1.000, 1.000, 1.000, 0.000, 1.000, 1.000, 1.000, "30 / 30"),
    "V1":   (0.025, 0.025, 0.416, 0.051, 0.362, 0.076, 0.106, "30 / 30"),
    "V2":   (0.038, 0.023, 0.715, 0.062, 0.720, 0.173, 0.104, "18 / 30"),
    "V4":   (0.052, 0.047, 0.725, 0.016, 0.606, 0.138, 0.096, "27 / 30"),
}
# Table 5 (tab:fm-system-metrics): (V1, V2, V4) as printed.
PAPER_FM = {
    "FM1 event-type recall (all 30)":      (0.011, 0.061, 0.100),
    "FM2 fabricated prefixes / text":      (1.97, 1.03, 0.93),
    "  of which malformed URI":            (18, 4, 10),
    "FM3 owl:sameAs statements (gold 190)": (0, 0, 6),
    "FM4 parsed (pipeline / rdflib-strict)": ("30 / 14", "18 / 14", "27 / 27"),
    "FM5 CIDOC predicate-set divergence (parsed)": (0.255, 0.557, 0.430),
    "FM6 vocab-injection rate (parsed)":   (0.199, 0.073, 0.025),
    "FM7 E52 detachment (parsed)":         (0.143, 0.107, 0.236),
}


# ── Loading ──────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sameas_statements(pred_subdir: str) -> int:
    """Count owl:sameAs *statements* (predicate occurrences) over 30 predictions."""
    total = 0
    for pred_file in sorted((PREDICTIONS_DIR / pred_subdir).glob("*.json")):
        output = _load(pred_file).get("output", "") or ""
        total += len(re.findall(r"owl:sameAs", output))
    return total


def _sameas_triples(el_summary_rows: List[dict], variant_key: str) -> int:
    """Sum rdflib-expanded owl:sameAs triples for one variant from EL rows."""
    return sum(r.get("n_pred_sameas", 0) for r in el_summary_rows
               if r.get("variant") == variant_key)


# ── Table 4: CH headline ─────────────────────────────────────────────────────

def _ch_row(score: dict):
    details = score["details"]
    f1_30 = sum(d["f1"] for d in details) / N_TEXTS
    return (
        round(score["f1"], 3),                    # F1_p (mean over parsed)
        round(f1_30, 3),                          # F1_30 (parse fail -> 0 / 30)
        round(score["oc"], 3),                    # OC
        round(score["rh"], 3),                    # RH
        round(score["entity_recall"], 3),         # ER
        round(score["type_f1"], 3),               # TF1
        round(score["predicate_coverage"], 3),    # PC
        f"{len(details)} / {N_TEXTS}",            # Parsed
    )


def build_ch_headline() -> Dict[str, tuple]:
    rows = {"Gold": _ch_row(_load(SCORES_DIR / GOLD_SCORE_FILE))}
    for label, (score_file, _fm_key, _pred) in VARIANTS.items():
        rows[label] = _ch_row(_load(SCORES_DIR / score_file))
    return rows


# ── Table 5: per-FM system metrics ───────────────────────────────────────────

def build_fm_metrics(fm: dict, el: dict):
    summary = fm["summary"]
    el_rows = el.get("rows", [])
    parsed_pipeline, parsed_rdflib, fm_by = {}, {}, {}
    sameas_stmt, sameas_trip = {}, {}
    for label, (score_file, fm_key, pred_subdir) in VARIANTS.items():
        details = _load(SCORES_DIR / score_file)["details"]
        parsed_pipeline[label] = len(details)
        s = summary[fm_key]
        parsed_rdflib[label] = s["n_parsed"]
        fm_by[label] = s
        sameas_stmt[label] = _sameas_statements(pred_subdir)
        sameas_trip[label] = _sameas_triples(el_rows, fm_key)

    def triple(field, ndigits):
        return tuple(round(fm_by[v][field], ndigits) for v in ("V1", "V2", "V4"))

    rows = {
        "FM1 event-type recall (all 30)":
            triple("FM1_event_recall_all_mean", 3),
        "FM2 fabricated prefixes / text":
            triple("FM2_mean_fabricated_per_text", 2),
        "  of which malformed URI":
            tuple(fm_by[v]["FM2_invalid_namespaces_total"] for v in ("V1", "V2", "V4")),
        "FM3 owl:sameAs statements (gold 190)":
            tuple(sameas_stmt[v] for v in ("V1", "V2", "V4")),
        "FM4 parsed (pipeline / rdflib-strict)":
            tuple(f"{parsed_pipeline[v]} / {parsed_rdflib[v]}" for v in ("V1", "V2", "V4")),
        "FM5 CIDOC predicate-set divergence (parsed)":
            triple("FM5_predicate_set_divergence_parsed_mean", 3),
        "FM6 vocab-injection rate (parsed)":
            triple("FM6_injection_rate_parsed_mean", 3),
        "FM7 E52 detachment (parsed)":
            triple("FM7_detachment_rate_parsed_mean", 3),
    }
    # The triple-consistent FM3 (matches the 'gold 199' basis) — reference, not in paper.
    extra = {"FM3 owl:sameAs triples (gold 199)":
             tuple(sameas_trip[v] for v in ("V1", "V2", "V4"))}
    return rows, extra, sameas_trip


# ── CSV writers ──────────────────────────────────────────────────────────────

CH_COLS = ["Variant", "F1_p", "F1_30", "OC", "RH", "ER", "TF1", "PC", "Parsed"]


def write_ch_csv(rows: Dict[str, tuple], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CH_COLS)
        for label in ("Gold", "V1", "V2", "V4"):
            w.writerow([label, *rows[label]])


def write_fm_csv(rows: Dict[str, tuple], extra: Dict[str, tuple], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Metric", "V1", "V2", "V4"])
        for metric, vals in rows.items():
            w.writerow([metric.strip(), *vals])
        for metric, vals in extra.items():
            w.writerow([metric.strip(), *vals])


# ── Verification against the paper's printed values ──────────────────────────

def _close(a, b) -> bool:
    """True if reproduced value matches the paper's printed value."""
    if isinstance(a, str) or isinstance(b, str):
        return str(a).replace(" ", "") == str(b).replace(" ", "")
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    return abs(float(a) - float(b)) <= 0.001  # within last printed digit


def verify(ch: Dict[str, tuple], fm: Dict[str, tuple], path: Path):
    checks = []
    for label in ("Gold", "V1", "V2", "V4"):
        for col, got, paper in zip(CH_COLS[1:], ch[label], PAPER_CH[label]):
            checks.append((f"T4 {label} {col}", got, paper, _close(got, paper)))
    for metric, got_vals in fm.items():
        paper_vals = PAPER_FM.get(metric)
        if paper_vals is None:
            continue
        for v, got, paper in zip(("V1", "V2", "V4"), got_vals, paper_vals):
            checks.append((f"T5 {metric.strip()} {v}", got, paper, _close(got, paper)))

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Cell", "Reproduced", "Paper", "Match"])
        for name, got, paper, ok in checks:
            w.writerow([name, got, paper, "PASS" if ok else "FAIL"])
    return checks


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                    help="Directory for the CSV outputs (default: results/paper_tables)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ch = build_ch_headline()
    fm_json = _load(FM_METRICS_JSON)
    el_json = _load(EL_SENSITIVITY_JSON)
    fm, extra, sameas_trip = build_fm_metrics(fm_json, el_json)

    ch_path = out_dir / "table4_ch_headline.csv"
    fm_path = out_dir / "table5_fm_system_metrics.csv"
    ver_path = out_dir / "verification.csv"
    write_ch_csv(ch, ch_path)
    write_fm_csv(fm, extra, fm_path)
    checks = verify(ch, fm, ver_path)

    fails = [c for c in checks if not c[3]]
    print(f"Wrote {ch_path}")
    print(f"Wrote {fm_path}")
    print(f"Wrote {ver_path}")
    print()
    print(f"Verification: {len(checks) - len(fails)}/{len(checks)} cells match the "
          f"paper's printed values.")
    for name, got, paper, ok in fails:
        print(f"  FAIL  {name}: reproduced={got} paper={paper}")
    if not fails:
        print("  All reproduced cells match the paper (Tables 4 and 5).")
    print()
    print("NOTE — FM3 counts owl:sameAs *statements* (predicate occurrences):")
    print(f"  V1/V2/V4 = {fm['FM3 owl:sameAs statements (gold 190)']} against "
          "gold = 190 statements; this is the")
    print("  self-consistent statement-vs-statement reading the paper uses.")
    print(f"  For reference, the rdflib *triple* count is V1/V2/V4 = "
          f"{tuple(sameas_trip[v] for v in ('V1','V2','V4'))} against gold = 199 "
          "triples")
    print("  (V4's 14 triples are all from architecture3's comma-list sameAs "
          "statements).")


if __name__ == "__main__":
    main()
