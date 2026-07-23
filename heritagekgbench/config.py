"""Repository-relative paths for the HeritageKGBench benchmark.

Replaces agentic-kgc's ``constants.CH_BENCHMARK_CONFIG``, which pointed at a
sibling ``ch-benchmark`` checkout. Here everything lives inside this repo.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BENCHMARK_DIR = REPO_ROOT / "benchmark"

CH_BENCHMARK_CONFIG = {
    "benchmark_jsonl": BENCHMARK_DIR / "benchmark.jsonl",
    "gold_dir": BENCHMARK_DIR / "gold",
    "texts_dir": BENCHMARK_DIR / "texts",
    "ontology": str(REPO_ROOT / "ontology" / "cacao-full.owl"),
    "domains": ["architecture", "fashion", "olympic", "sound"],
}

# CACAO imports term lists (FOAF/ODRL/PROV/schema.org subsets), used by
# fm_metrics FM2/FM6. Vendored from the CACAO ontology repository
# (src/ontology/imports/*_terms.txt).
CACAO_IMPORTS_DIR = REPO_ROOT / "ontology" / "imports"

PREDICTIONS_DIR = REPO_ROOT / "predictions"
RESULTS_DIR = REPO_ROOT / "results"
