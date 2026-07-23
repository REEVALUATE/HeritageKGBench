# HeritageKGBench Evaluation Metrics

Full definitions of every metric computed by the evaluation harness in
`heritagekgbench/`. These are the metrics reported in the accompanying paper
(§5.1, §5.5). The implementations are ports of the exact code used to produce
the paper's numbers.

## Parsing convention (read this first)

Both gold TTL files and system predictions are parsed through the **same**
pipeline (`heritagekgbench.graph_metrics.parse_rdf_output`):

1. Markdown code fences are stripped; fallback `ns1:`/`ns2:`/`ns3:`/`wd:`/`wdt:`
   prefixes are injected when a prefix-less fragment references them;
   duplicate `@prefix` declarations are removed.
2. The result is parsed with rdflib (Turtle). A failure yields zero triples.
3. Every URI/bnode is resolved to a human-readable label (`rdfs:label`
   preferred, `@en` wins over other language tags; URI local name as
   fallback; blank nodes get stable labels built from their properties).
4. `rdf:type` and `rdfs:label` statements are **dropped** — they are evaluated
   separately at Tier 2.

Because the gold passes through the same parser, the effective gold size is
smaller than the raw rdflib triple count: the released gold contains **1,093
statements** under this convention (raw rdflib: 2,198 triples including
`rdf:type`/`rdfs:label`). Any reimplementation must reproduce this parsing
convention for numbers to be comparable.

## Tier 1 — triple-level precision / recall / F1

`calculate_metrics_smart(gold_triples, pred_triples)`:

- Both triple lists are normalized: lowercase, punctuation stripped, dates
  normalized via `dateutil` (`YYYY-MM-DD`, or bare year for 4-digit strings).
- Predicted triples whose (normalized) relation does not occur in the gold's
  relation set are filtered out before scoring, as are Wikidata property IDs
  (`p123`).
- Matching is greedy one-to-one, grouped by relation: a predicted triple
  matches a not-yet-matched gold triple with the same normalized relation if
  both subject and object pass `smart_similarity`:
  equality, substring containment, token-overlap > 0.66 of the smaller token
  set, or `difflib.SequenceMatcher` ratio > 0.85.
- P = TP/(TP+FP), R = TP/(TP+FN), F1 = 2PR/(P+R).

### Aggregation: F1_p and F1_30

Per-text scores are macro-averaged. Items whose prediction file is missing or
whose output is empty are not scorable. Two views are reported:

- **F1_p** — mean over scorable (parsed) items only. This is the `f1` key in
  score files, with `count` giving the number of scorable items.
- **F1_30** — parse failures count as F1 = 0 over all 30 texts (`f1_30` key).

Note the distinction between *scorable* (non-empty output; Table "Parsed"
column: 30/18/27 for V1/V2/V4) and *strict rdflib parse* (used by FM4 and the
EL-sensitivity script: 14/14/27) — an output can be scorable but yield zero
triples when rdflib rejects it.

## Tier 2 — structural metrics (raw graphs)

Computed on raw rdflib graphs (`graph_level_metrics.py`), so `rdf:type` and
`rdfs:label` are visible here:

- **Entity recall (ER)** — fraction of gold entities found in the prediction.
  Entities are labelled via `rdfs:label` (URI local name as fallback);
  matching is exact (case-insensitive) first, then `smart_similarity`.
- **Type-F1 (TF1)** — micro P/R/F1 over the `rdf:type` sets of label-matched
  entity pairs (type URIs compared by local name, e.g. `E21_Person`).
- **Predicate coverage (PC)** — fraction of the gold's distinct predicate
  local names (excluding `rdf:type`, `rdfs:label`, `owl:sameAs`) also used in
  the prediction.

## Tier 3 — ontology conformance and hallucination

Following Text2KGBench's definitions (`hallucination_metrics.py`), computed
over the Tier-1 parsed triples:

- **OC (ontology conformance)** — fraction of predicted relations whose
  normalized label occurs in the ontology's relation label set
  (`ontology/cacao-full.owl`). `owl:sameAs` is whitelisted as conforming
  because the benchmark uses it for entity links.
- **RH (relation hallucination)** = 1 − OC contribution per triple.
- **SH / OH (subject / object hallucination)** — fraction of subjects/objects
  whose Snowball-stemmed form is not a substring of the stemmed source text
  nor of any stemmed ontology concept label.

Lower is better for SH/RH/OH; higher is better for OC.

## Failure-mode metrics (FM1, FM2, FM5, FM6, FM7)

`heritagekgbench/fm_metrics.py` quantifies five of the paper's failure modes
per (text, variant); FM3 (entity linking) and FM4 (parse failure) are already
covered by the sameAs statistics and parse counts:

- **FM1 event-type recall** — fraction of the gold's CIDOC event classes
  (E5/E7/E8/…/E87 concrete event subclasses; 26-class list in the script)
  present in the prediction's `rdf:type` assertions.
- **FM2 fabricated-namespace count** — distinct `@prefix` declarations outside
  the allowed set (structural: rdf/rdfs/owl/xsd; CACAO + imports:
  crm/cacao/foaf/odrl/prov/schema; external: wd/aat/iconclass/ex/dc/dcterms/
  skos). Auto-numbered `nsN:` prefixes always count as fabricated; prefixes
  whose URI is not http(s) count as invalid.
- **FM5 predicate substitution** — (a) for (subject-label, object-label) pairs
  present in both graphs, the fraction connected by a different CIDOC
  predicate; (b) predicate-set divergence: CIDOC predicates used by the system
  but absent from the gold's CIDOC predicate set, over the system's CIDOC
  predicate set.
- **FM6 vocabulary-injection rate** — fraction of predicted triples whose
  predicate is outside the CACAO allowed predicate space (CIDOC-CRM/CACAO
  namespaces + `rdf:type`/`rdfs:label`/`owl:sameAs` + the specific
  FOAF/ODRL/PROV/schema.org terms CACAO imports, vendored in
  `ontology/imports/*_terms.txt`).
- **FM7 temporal-detachment rate** — fraction of `E52_Time-Span` nodes not
  attached to anything via `P4_has_time-span` / `P4i_is_time-span_of`.

## Uncertainty

`heritagekgbench/significance_tests.py`: mean per-text F1 with 95% percentile
bootstrap CIs (10,000 resamples, seed 20260507), under both F1_p and F1_30.
(The paired Wilcoxon signed-rank tests across Text2KGBench domains reported in
the paper live in the agentic-kgc repository; Text2KGBench is not part of this
release.)

## Entity-linking sensitivity

`heritagekgbench/el_sensitivity.py`: recomputes Tier-1 F1 with `owl:sameAs`
triples filtered out of both gold and prediction, quantifying the mechanical
recall floor created by gold entity links (199 `owl:sameAs` statements in the
released gold, mean 6.6/text) while entity linking is disabled in the
evaluated systems.

## Inter-annotator agreement (reported, not recomputable here)

Agreement between the nine annotators was measured at entity level
(correspondence by `owl:sameAs`, exact label match, or fuzzy token-Jaccard
≥ 0.5): pairwise entity F1 0.20 (upper-bounded at ~0.73 by differing graph
sizes), type-set Jaccard 0.34 on matched entities, primary-class Cohen's κ
0.58 (n = 204). Per-annotator submissions are not part of this release, so
these numbers are reported for context rather than recomputable from the
repository.
