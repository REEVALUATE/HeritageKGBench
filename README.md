# HeritageKGBench

HeritageKGBench is a benchmark for **knowledge graph construction from
cultural heritage texts** against an event-centric reference ontology
([CACAO](http://w3id.org/cacao), a [CIDOC-CRM](https://www.cidoc-crm.org/)
extension). It accompanies the paper *"LLM-based Knowledge Graph Construction
for Cultural Heritage: An Extraction-Failure Diagnostic and CIDOC-CRM
Benchmark"* and contains:

- **30 English-language texts** from four cultural heritage institutions,
  spanning archaeology (Fondazione Aquileia), fashion (MoMu Antwerp), Olympic
  history (Olympic Museum of Thessaloniki), and ethnomusicology (Berliner
  Phonogramm-Archiv);
- **30 curated gold-standard RDF graphs** (Turtle), annotated by nine trained
  annotators against CACAO/CIDOC-CRM with entity links to Wikidata, Getty AAT
  and ICONCLASS, then curated by the authors against a released
  [modelling guide](docs/MODELLING_GUIDE.md);
- the **evaluation harness** that computes every metric reported in the paper
  (triple-level fuzzy P/R/F1, structural metrics, hallucination/ontology
  conformance, failure-mode metrics, bootstrap CIs — see
  [docs/METRICS.md](docs/METRICS.md));
- the **baseline pipeline** (`heritagekgbench/pipeline/`): the V1 single-prompt,
  V2 sequential-agent, and V4 SHACL-repair systems evaluated in the paper
  (Google ADK + LiteLLM); prompts, ontology-summary construction, SHACL shape
  generation and retry budgets are additionally documented in
  [docs/PROMPTS_AND_SHAPES.md](docs/PROMPTS_AND_SHAPES.md);
- the **official baseline predictions** (V1/V2/V4; generator: Gemini 2.5
  Flash) and their score files, so the paper's result tables can be verified
  without any API calls.

## Folder structure

```
benchmark/
  benchmark.jsonl        index: one record per text (id, domain, paths, stats)
  texts/<domain>/        30 source texts (.txt)
  gold/<domain>/         30 gold-standard graphs (.ttl)
ontology/
  cacao-full.owl         CACAO ontology (the exact file used for evaluation)
  ontology_summary.txt   compact ontology summary given to the LLM systems
  imports/               CACAO's imported FOAF/ODRL/PROV/schema.org term lists
heritagekgbench/         evaluation harness (Python package)
  pipeline/              baseline KGC systems V1/V2/V4 (optional extras)
predictions/
  single_prompt/         V1 outputs (30 JSON files: {"id", "output"})
  baseline/              V2 outputs
  shacl/                 V4 outputs
  gold_as_pred/          gold graphs as predictions (sanity set, scores 1.0)
results/
  scores/                canonical score files for V1/V2/V4 + gold sanity
  fm_metrics.json        failure-mode metrics (FM1/2/5/6/7)
  significance_tests.json  bootstrap 95% CIs
  el_sensitivity.{json,csv} F1 with/without owl:sameAs links
  paper_tables/          paper Tables 4 & 5 as CSVs + verification vs. the PDF
docs/
  MODELLING_GUIDE.md     annotation provenance + modelling conventions
  METRICS.md             full metric definitions
  PROMPTS_AND_SHAPES.md  prompts & SHACL shapes of the evaluated systems
```

## How to use

Requires Python ≥ 3.10.

```bash
pip install -e .
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
```

**Evaluate your own system.** Produce one JSON file per benchmark text in a
directory, named `<text_id>.json` (e.g. `architecture1.json`), each containing
`{"id": "<text_id>", "output": "<your Turtle string>"}` (the helper
`heritagekgbench.evaluate.save_prediction` does this for you). Then:

```bash
heritagekgbench evaluate --pred-dir path/to/your/predictions --output scores.json
```

The score dict reports Tier-1 triple P/R/F1 (`f1` = F1_p over scorable items,
`f1_30` = failures-as-zero over all 30 texts), Tier-2 structural metrics
(entity recall, type-F1, predicate coverage), Tier-3 ontology
conformance/hallucination (OC, SH, RH, OH), and per-item details. See
[docs/METRICS.md](docs/METRICS.md) for definitions — in particular the shared
gold/prediction parsing convention, without which numbers are not comparable.

**Reproduce the paper's tables.**

```bash
# Baseline scores (writes/refreshes results/scores/*.json)
heritagekgbench evaluate --pred-dir predictions/single_prompt --output results/scores/run1_single_prompt.json
heritagekgbench evaluate --pred-dir predictions/baseline      --output results/scores/run1_baseline.json
heritagekgbench evaluate --pred-dir predictions/shacl         --output results/scores/run1_shacl.json

# Sanity check: gold vs itself = F1 1.0
heritagekgbench evaluate --pred-dir predictions/gold_as_pred

# Failure-mode metrics, bootstrap CIs, sameAs sensitivity
heritagekgbench fm-metrics
heritagekgbench significance
heritagekgbench el-sensitivity

# Paper Tables 4 & 5 as CSVs, checked cell-by-cell against the PDF
# -> results/paper_tables/{table4_ch_headline,table5_fm_system_metrics,verification}.csv
heritagekgbench paper-tables
```

**Re-run the baseline systems** (optional; requires an LLM API key and incurs
API cost — the shipped predictions make this unnecessary for verification):

```bash
pip install -e ".[pipeline]"
export OPENROUTER_API_KEY=...   # paper runs used Gemini 2.5 Flash via OpenRouter
heritagekgbench run --variant single_prompt --output-dir predictions/my_v1_rerun
heritagekgbench run --variant baseline      --output-dir predictions/my_v2_rerun
heritagekgbench run --variant shacl         --output-dir predictions/my_v4_rerun
```

LLM outputs are not deterministic; reruns will not byte-reproduce the shipped
predictions, which is why the official prediction files are included.

Headline numbers against the released gold (macro-averaged; "scored" = texts
with non-empty system output):

| Variant | Scored | F1_p | F1_30 | Entity recall | OC |
|---|---|---|---|---|---|
| V1 single prompt | 30/30 | 0.0255 | 0.0255 | 0.362 | 0.416 |
| V2 agentic pipeline | 18/30 | 0.0381 | 0.0229 | 0.720 | 0.715 |
| V4 agentic + SHACL | 27/30 | 0.0525 | 0.0472 | 0.606 | 0.725 |
| gold (sanity) | 30/30 | 1.0000 | 1.0000 | 1.000 | 1.000 |

## Notes and known limitations

- `sound9` and `sound10` share a source text (factual vs subjective
  interpretation) — see the errata in
  [docs/MODELLING_GUIDE.md](docs/MODELLING_GUIDE.md).
- Inter-annotator agreement was low (pairwise entity F1 0.20, primary-class
  κ 0.58), reflecting genuine modelling freedom in CIDOC-CRM; exact-match
  evaluation is therefore too strict, which motivates the fuzzy Tier-1
  matching and the multi-tier metric design.
- The gold accepts every defensible external link per concept (no canonical
  Wikidata Q); `owl:sameAs` links create a mechanical recall floor quantified
  by `heritagekgbench el-sensitivity`.

## How to cite

If you use HeritageKGBench, please cite the accompanying paper (see
[CITATION.cff](CITATION.cff)):

> Ruben Peeters, Xuemin Duan, Anastasia Dimou. *LLM-based Knowledge Graph
> Construction for Cultural Heritage: An Extraction-Failure Diagnostic and
> CIDOC-CRM Benchmark.* In: 25th International Conference on Knowledge
> Engineering and Knowledge Management (EKAW 2026), 29 September – 1 October
> 2026. In press.

For the CACAO ontology, cite: *Rights to Richness: Connecting Cultural
Artefacts with Rights and Context* (REEVALUATE project).

## License

Code is released under the [MIT License](LICENSE). The source texts were
provided by the four partner institutions for research use within the
REEVALUATE project.
