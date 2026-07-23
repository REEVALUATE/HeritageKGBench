#!/usr/bin/env python3
"""
significance_tests.py — Per-text bootstrap confidence intervals on
HeritageKGBench.

Ported from agentic-kgc ``scripts/significance_tests.py``. That script also
ran paired Wilcoxon signed-rank tests across the 10 Text2KGBench domains;
the Text2KGBench data is not part of this repository, so only the CH-benchmark
bootstrap part is kept here. The bootstrap procedure (10k resamples, seed
20260507, percentile 95% CI) and the RNG call order are unchanged.

Inputs: per-item F1 values from ``results/scores/run1_*.json`` (the
``details`` list written by the evaluator).

Outputs: mean F1 with 95% bootstrap CI for V1, V2, V4, under both
F1_p (parsed items only) and F1_30 (parse failure -> 0 over all 30 texts).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List

from heritagekgbench.config import RESULTS_DIR

random.seed(20260507)

SCORES_DIR = RESULTS_DIR / "scores"
OUT_JSON = RESULTS_DIR / "significance_tests.json"

# Paper label -> score file (Run 1, gemini-2.5-flash).
VARIANT_SCORES = {
    "V1": "run1_single_prompt.json",
    "V2": "run1_baseline.json",
    "V4": "run1_shacl.json",
}

ALL_30_IDS = (
    [f"architecture{i}" for i in range(1, 6)]
    + [f"fashion{i}" for i in range(1, 6)]
    + [f"olympic{i}" for i in range(1, 6)]
    + [f"sound{i}" for i in range(1, 16)]
)


# ── Bootstrap CI on the mean ────────────────────────────────────────────────

def bootstrap_mean_ci(values: List[float], n_iter: int = 10000,
                      alpha: float = 0.05) -> Dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}
    n = len(values)
    means = []
    for _ in range(n_iter):
        sample = [values[random.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(n_iter * (alpha / 2))]
    hi = means[int(n_iter * (1 - alpha / 2))]
    return {"n": n,
            "mean": round(sum(values) / n, 4),
            "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4)}


# ── Load data ────────────────────────────────────────────────────────────────

def load_ch_per_item(scores_dir: Path) -> Dict[str, Dict[str, float]]:
    """Returns {variant_paper_label: {text_id: f1}} from the score files.

    The score files contain PARSED items only (30 for V1, 18 for V2, 27 for
    V4); unparsed items are absent, matching the paper's Table 4 Parsed
    column.
    """
    out: Dict[str, Dict[str, float]] = {}
    for label, fname in VARIANT_SCORES.items():
        data = json.loads((scores_dir / fname).read_text(encoding="utf-8"))
        out[label] = {row["id"]: float(row["f1"]) for row in data["details"]}
    return out


# ── Compose tests ───────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores-dir", default=str(SCORES_DIR))
    ap.add_argument("--output-json", default=str(OUT_JSON))
    args = ap.parse_args()

    ch = load_ch_per_item(Path(args.scores_dir))

    # The paper reports F1_p as mean over parsed rows and F1_30 as the
    # sum-over-parsed divided by 30 (parse failures count as 0). Bootstrap is
    # over the parsed rows for F1_p, and over an explicit 30-text sample
    # (parsed values + zeros for missing texts) for F1_30.
    ch_summary = {}
    for label, m in ch.items():
        parsed_values = list(m.values())  # only parsed
        all_30_values = [m.get(tid, 0.0) for tid in ALL_30_IDS]
        ch_summary[label] = {
            "F1_p":  bootstrap_mean_ci(parsed_values),
            "F1_30": bootstrap_mean_ci(all_30_values),
            "n_parsed": len(parsed_values),
            "n_total": len(all_30_values),
        }

    out = {"ch_bootstrap": ch_summary}
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Wrote {out_path}")
    print()
    print("HeritageKGBench bootstrap (10k resamples, 95% CI):")
    for label, s in ch_summary.items():
        f1p = s["F1_p"]
        f130 = s["F1_30"]
        print(f"  {label}  F1_p  mean={f1p['mean']:.4f} "
              f"95%CI=[{f1p['ci_lo']:.4f},{f1p['ci_hi']:.4f}] (n={f1p['n']})")
        print(f"        F1_30 mean={f130['mean']:.4f} "
              f"95%CI=[{f130['ci_lo']:.4f},{f130['ci_hi']:.4f}] (n={f130['n']})")


if __name__ == "__main__":
    main()
