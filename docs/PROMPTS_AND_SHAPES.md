# Prompts, SHACL Shapes, and Retry Budgets

Supplementary material for the paper *LLM-based Knowledge Graph
Construction for Cultural Heritage: An Extraction-Failure Diagnostic and
CIDOC-CRM Benchmark*. Documents the ontology-summary construction, the
per-agent prompts, the SHACL shape generation, the repair prompt, and the
retry budgets and stopping conditions of the evaluated systems.
This document mirrors the pipeline source released in
`heritagekgbench/pipeline/` and is intended as a reading companion; the
source files are authoritative.

## 1. Ontology summary construction

The ontology summary supplied to every variant (V1 monolithic and V2--V5
agentic) is produced by `agentic_kgc.agents.ontology.utils.summarize_ontology_for_llm`.
For each ontology file (CIDOC-CRM and the domain-specific extension), the
summariser emits:

- the list of declared classes (URI suffix + `rdfs:label` if present),
- the list of declared properties with `rdfs:domain` / `rdfs:range`,
- a small set of representative example triples per class.

The same summary is supplied to V1 and to the V2--V5 NER, Relation Extraction,
and Ontology Mapping agents, holding the ontology context fixed across the
variant comparison.

## 2. Variant V1 — Monolithic single-prompt baseline

Source: `agentic_kgc/runner.py`, branch `variant == "single_prompt"`.

```
You are a knowledge graph construction expert. Given the following ontology
and text, extract all knowledge as RDF triples in Turtle format.

ONTOLOGY:
{ontology_summary}

TEXT:
{text}

Output ONLY valid RDF/Turtle. Use the ontology classes and properties listed
above. Include @prefix declarations.
```

No retry, no validation, no decomposition.

## 3. Variant V2 — Six-agent baseline pipeline

Implemented on Google ADK with LiteLLM routing
(`agentic_kgc/agent_factories.py`, `agentic_kgc/sequential_agent/agent.py`).

### 3.1 NER agent (`agentic_kgc/agents/ner/prompt.py`)

Verbatim opening (~60 lines total in source):

```xml
<system_role>
  You are a high-precision, ontology-based Named Entity Recognition (NER)
  system. Your function is to process input text, identify all entities,
  and classify them using ONLY the class identifiers from the provided
  ontology.
</system_role>
<output_specification>
  Output is a JSON array of {"entity": "<text span>",
                             "class": "<ontology class id>"}.
  Begin immediately with `[` and end immediately with `]`.
  No preamble, explanation, or markdown.
</output_specification>
```

Examples in the prompt include `{"entity":"Queen Victoria",
"class":"cidoc:E21_Person"}` and `{"entity":"beige silk muslin",
"class":"cidoc:E57_Material"}`.

### 3.2 Entity Linking agent (`agents/entity_linking/prompt.py`)

Resolves entities against Wikidata, Getty AAT, and a local instance of the
domain-specific extension, exposed as tool calls. **Disabled during benchmark
evaluation** for parity with the monolithic baseline; see
`agent_factories.py::create_pipeline(include_entity_linking=False)` (the
default for benchmark runs).

### 3.3 Coreference Resolution agent (`agents/coreference/prompt.py`)

Clusters entity mentions within a single input text. No external resource
calls.

### 3.4 Relation Extraction agent (`agents/relation_extraction/prompt.py`)

Verbatim excerpt:

```xml
<task_definition>
  Receive <input_data> with <text> and <entities>. Scan <text> for explicit
  semantic relationships between any two entities from the <entities> list.
  Check if the relationship is defined in the <ontology>. Emit one JSON
  triple {"head","relation","tail"} per explicit, ontology-valid relation.
</task_definition>
<constraints>
  Strictly Explicit. Ontology-Bound. Entity-Bound. No Inverse Relations.
  No Duplicates. No Commentary.
</constraints>
```

### 3.5 Ontology Mapping agent

Synthesises the assembled relation list and entity list into RDF/Turtle
aligned to CIDOC-CRM and the domain-specific extension. Namespace bindings
follow the ontology summary.

### 3.6 RDF Validator agent (`agents/rdf_validator/prompt.py`)

Closes the V2 baseline by checking Turtle syntax, namespace resolution, and
RDF well-formedness. **Structural only**: it does not enforce ontology
shapes. Triggers on rdflib parse failure of the assembled graph and asks the
upstream Ontology Mapping agent to regenerate. The 12/30 V2 parse failures
on CH (Sec. 5.4 of the paper) reach this stage but exhaust the retry budget
without converging.

## 4. Variant V4 — SHACL repair loop

Source: `agentic_kgc/validation_loop.py`, `agents/shacl/prompt.py`.

### 4.1 Shape graph construction

The shape graph is produced by `agentic_kgc/owl_to_shacl.py::OWLToSHACLConverter`,
which extracts the following constraints from the OWL ontology axioms
(CIDOC-CRM + domain-specific extension):

- domain and range constraints on each property,
- cardinality restrictions where declared,
- property restrictions (functional / inverse-functional),
- class hierarchies as `sh:targetClass` declarations.

The converter emits one `sh:NodeShape` per declared class, with
`sh:property` declarations enumerating the allowed predicates and
`sh:class` constraints on object types. The shape graph is loaded once
per run and bound to the validation tool (`validate_with_shacl`).

### 4.2 SHACL Validation agent (`agents/shacl/prompt.py`)

The validation agent invokes `validate_with_shacl()` and reports:

- `VALID` (string) if the assembled graph conforms, or
- a JSON object with `total_violations` and a list of
  `{focus_node, path, message, severity}` records.

The agent does **not** attempt repair; it only validates and reports.

### 4.3 SHACL Repair agent (`agents/shacl/prompt.py`)

Verbatim repair-strategy excerpt:

```
1. Parse Violations: read each violation and identify the problematic
   triple(s).
2. Determine Fix:
   - Missing rdf:type      → add appropriate type assertion
   - Invalid domain/range  → correct or remove the triple
   - Cardinality           → add/remove triples to satisfy min/max
   - Malformed URI         → fix syntax
3. Apply Corrections; preserve all triples that did not violate.
```

Output is the corrected Turtle inside a markdown ```turtle block; no other
text is allowed.

### 4.4 Retry budget

`agentic_kgc/validation_loop.py::MAX_VALIDATION_ITERATIONS = 3`. After three
rounds the most recent graph is returned regardless of remaining
violations. Stopping conditions are: (i) `VALID` reported by the validation
agent, (ii) iteration cap reached, or (iii) parse failure on a repair
attempt (the prior graph is kept).

## 5. Variants V3, V5 — Design-by-Contract gatekeepers

Source: `agentic_kgc/dbc_pipeline.py`,
`agents/gatekeeper/`. Two gatekeepers are deployed:

- **NER gatekeeper.** Pre-condition: the input is a non-empty text. Post-
  condition: every emitted entity instantiates a class declared by the
  ontology, and the required fields for that class are populated.
- **Relation Extraction gatekeeper.** Post-condition: every emitted
  relation's head and tail appear in the upstream NER output, and the
  field names match the contract.

On violation, the gatekeeper returns the list of per-field errors to the
retrying upstream agent. As of commit `1ec747d0` the feedback is
descriptive (e.g. "Entity 'X' has class 'Y' not found in the ontology",
"Relation N references unknown entity 'X' (not in NER output)") rather
than a binary verdict; see paper §3.3 / §4.3 for the implementation
distinction from HyDRA's global-invariant contracts.

The retry budget is bounded but each gatekeeper makes its decision on the
upstream agent's output **in isolation**: neither gatekeeper sees the
assembled graph the downstream agents will produce. This stage-locality
is the property the paper analyses in §6.1.

## 6. Reproducibility pointers

- Pipeline source: `agentic_kgc/`
- Retry budget constants: `agentic_kgc/validation_loop.py`,
  `agentic_kgc/dbc_pipeline.py`
- SHACL shape generation: `agentic_kgc/owl_to_shacl.py`
- Per-agent prompts: `agentic_kgc/agents/*/prompt.py`
- Variant entry points: `agentic_kgc/runner.py::process_single_text`
- CH-benchmark loader and evaluator: `agentic_kgc/ch_benchmark.py`
- Significance / EL-sensitivity scripts: `scripts/significance_tests.py`,
  `scripts/el_sensitivity.py`
- IAA scripts: `ch-benchmark/scripts/interannotator_agreement.py`,
  `ch-benchmark/scripts/entity_agreement.py`
