# HeritageKGBench Modelling Guide

This document describes how the gold-standard annotations were produced and
the modelling conventions they follow. It is released alongside the benchmark
as required reading for interpreting evaluation results: system-output failure
modes can be read as divergence from these conventions.

## Annotation provenance

The benchmark is based on 30 texts provided by four European museums and
institutions. Nine trained annotators translated the unstructured texts to RDF
graphs using the [CACAO](http://w3id.org/cacao) ontology (a
[CIDOC-CRM](https://www.cidoc-crm.org/) extension), adding links to existing
knowledge bases: [Wikidata](https://www.wikidata.org/),
[Getty AAT](https://www.getty.edu/research/tools/vocabularies/aat/) and
[ICONCLASS](https://iconclass.org/).

Each annotator was assigned nine of the thirty texts, yielding approximately
three independent annotations per text (twenty-one texts received three
independent annotations; nine received two). For each text, the authors
selected one preferred annotation as the closest fit to the modelling guide,
merged useful external links and content from the other annotations, and then
performed corrective passes against the modelling guide (link validation and
enrichment, correction of high-level CACAO/CIDOC structural errors). Gold TTL
file headers credit the contributing annotators under stable pseudonyms
(annotator1–annotator9).

The modelling guide was made after the fact, as the disagreement between
annotators was high. This ensures biases and assumptions are explicit and can
be taken into account when using the benchmark. The annotations were curated
towards this modelling guideline.

# Approach

1. Preferred graph chosen among the usable student annotations, where possible. 
2. Extract useful external links and additional information from the other annotations.
3. Curate towards modelling guidelines
4. Validation of external links, and addition of external links, where useful
5. Internal consistency check across modelling guidelines


# Manual changes after  convergence
- Replace E22 with Physical Artefact
- Replace cacao:Domus with cacao:CACAO_0000055
- Removed cacao:Audio as they refer to digital artefacts, not physicals
- Removed non-existing cacao identifiers
- Replaced P82a_begin_of_the_begin / P82b_end_of_the_end with P81_ongoing_throughout + P82_at_some_time_within (P82a/b are not in cacao).


# Modelling guidelines

The gold annotations follow these modelling conventions, chosen for the project's CIDOC-CRM use case. Each rule was either established at curation time or later quantified from a frequency profile of the gold corpus.

## Time, measurement, and structural shape

- **Time-spans** use P81_ongoing_throughout + P82_at_some_time_within with the same value. P81 carries the minimum extent, P82 the maximum extent. Single-day events: `"YYYY-MM-DD"^^xsd:date`. Date ranges: `"YYYY-MM-DD/YYYY-MM-DD"` as a literal string (xsd:date does not encode intervals). Year-only knowledge ("1896", "1930s") is treated as a range covering the period: `"1896-01-01/1896-12-31"` for a single year, `"1930-01-01/1939-12-31"` for a decade. The paired-bounds form is required for every E52_Time-Span, even when the bounds collapse to a single day — a label-only or single-property time-span is considered incomplete. (Corpus: 48 E52 nodes, 48 with the paired form.)
- **Dimensions** use the full E54_Dimension pattern: P90_has_value (typed literal), P91_has_unit (pointing to an E58_Measurement_Unit), P2_has_type (pointing to an E55_Type), and rdfs:label. Counts of items use a generic `ex:type_count` with the unit naming the thing being counted (`ex:unit_wax_cylinder`, `ex:unit_pipe`, etc.). A stripped-down E54 (P90 only, no unit/type) is considered incomplete. (Corpus: 21 E54 nodes, 21 with the full pattern.)

## Activities and creations

- **Activities** (E7_Activity) and **creations** (E65_Creation) are connected to their participants and circumstances rather than emitted as standalone labelled nodes:
  - `crm:P14_carried_out_by` → an actor (E21_Person, E74_Group). 35 of 42 E7s and 19 of 16 E65s carry this in the corpus (multi-actor activities account for the >1 ratio on E65).
  - `crm:P7_took_place_at` → a place (E53_Place). 32/42 E7s and 13/16 E65s.
  - `crm:P4_has_time-span` → an E52_Time-Span (which itself follows the paired-bounds rule above). 19/42 E7s and 14/16 E65s.
  - `crm:P94_has_created` → the resulting object/document (E65 only). 17/16 E65s.
  - `crm:P11_had_participant`, `crm:P12_occurred_in_the_presence_of`, `crm:P16_used_specific_object` are used when distinct from the carrier. 
  - **An E7/E65 node carrying only `rdfs:label` is considered incomplete.** Standard form: `?act a crm:E7_Activity ; crm:P14_carried_out_by ?who ; crm:P7_took_place_at ?where ; crm:P4_has_time-span ?when ; rdfs:label "..."@en`.

## Physical objects

- **Physical artefacts** are typed `cacao:CACAO_0000023` (Physical Artefact). They expect:
  - `crm:P2_has_type` → an `ex:type_*` E55_Type that names the kind of object (26/45 in corpus).
  - `crm:P56_bears_feature` → an E25_Man-Made_Feature when the source describes a decorative or structural feature (13/45; mostly fashion).
  - `crm:P128_carries` → an E33_Linguistic_Object when the artefact carries text (10/45; e.g. inscriptions on stone weights).
  - `crm:P43_has_dimension` → an E54_Dimension (9/45; mostly fashion + sound).
  - `crm:P45_consists_of` → an E57_Material when material is named (5/45; fashion).

## Domain-specific structure

- **Fashion items** make heavy use of `crm:E25_Man-Made_Feature` (19/19 in fashion gold) for decorative and structural features such as "diagonal stripe pattern" or "raglan sleeves". The feature itself is typed E25 with a `crm:P2_has_type` to an E55_Type and an optional `rdfs:label`.
- **Sound recordings** use `crm:E78_Curated_Holding` for cylinder collections held by an archive. The collection carries `crm:P50_has_current_keeper` to the archive (E74_Group), `crm:P46_is_composed_of` to constituent recordings, and `crm:P43_has_dimension` to count nodes.
- **Olympic / sound documents** introduce `crm:E33_Linguistic_Object` for the linguistic content of a document, separate from the document itself (`crm:E31_Document`). The document `crm:P128_carries` the linguistic object.

## Entity linking

- **Entity links** use `owl:sameAs` to Wikidata, AAT, or ICONCLASS. The evaluation pipeline whitelists `owl:sameAs` as a conforming predicate.
- **AAT URIs are first-class linking targets, not internal-routing intermediates.** Where AAT covers a concept, the entity carries BOTH the Wikidata `owl:sameAs` and the AAT `owl:sameAs` (and ICONCLASS where applicable). The two are emitted as independent triples; the linking metric counts pairs from each KB independently, so a model gets credit for emitting either or both. Curators should add `aat:xxx` alongside the existing `wd:Qxxx` whenever the AAT thesaurus has a concept that matches the entity's meaning. This applies to E57_Material, E55_Type, E22_Human-Made_Object, E25_Man-Made_Feature, and CACAO_0000023 — any class whose instances correspond to concepts the AAT facets cover (Materials, Object Types, Activities, Styles & Periods, Physical Attributes, Associated Concepts).
- **`owl:sameAs` is identity; compound entities use `crm:P127_has_broader_term` for component concepts.** A label like `"silk muslin"` is NOT identical to silk and NOT identical to muslin — silk and muslin are *broader concepts* of which silk muslin is a specific kind. For compound material/type labels that decompose into multiple AAT or Wikidata concepts, link each component with `crm:P127_has_broader_term` rather than `owl:sameAs`. P127's CIDOC domain/range is `E55_Type → E55_Type`; this applies to E57_Material via E57 ⊑ E55_Type. Use `owl:sameAs` only when a single concept covers the entity (e.g. `"blue taffeta"` IS-A `aat:taffeta` modulo a colour qualifier; `"mother-of-pearl"` IS `aat:mother of pearl`). For object-class entities (E22, E25, CACAO) that don't share E55_Type's hierarchy, do not emit P127 — use only `owl:sameAs` when the entity is essentially one concept.
- **All valid links are accepted; no canonical Wikidata Q.** When a single concept has multiple defensible Wikidata items (e.g. `wd:Q37681` *silk fiber* vs `wd:Q12321255` *silk fabric* — both legitimate for "silk" in different conceptual axes), the gold carries every valid link, and the linking metric credits a model for emitting any of them. Curators do not pick one Wikidata Q as canonical; they add all that correctly identify the concept. This includes AAT-routed Wikidata items obtained via AAT's `skos:exactMatch` cross-walks: when AAT cross-walks to a different Q than the curator's prior choice, both are added as `owl:sameAs` triples so long as both genuinely identify the entity's concept. Curator judgement applies during review — if AAT's cross-walk leads to a conceptually distinct neighbour rather than a true sibling (e.g. routing-error or AAT mis-categorisation), reject that proposal.
- **AAT enrichment covers E57_Material, E22_Human-Made_Object, E25_Man-Made_Feature, E55_Type, and CACAO_0000023.** These are the classes whose instances correspond to concepts in AAT's facets (Materials, Object Types, Activities, Styles & Periods, Physical Attributes, Associated Concepts). Other classes are explicitly out of AAT's scope and need separate vocabularies for their KB enrichment: **E21_Person** belongs to ULAN (Union List of Artist Names, ~140k persons) and Wikidata, **E53_Place** belongs to TGN (Thesaurus of Geographic Names, ~3M places), Wikidata, or GeoNames, and **E52_Time-Span / E54_Dimension / E58_Measurement_Unit** typically have no external KB equivalents (local URIs only). E21/E53 KB enrichment is acknowledged as future work; the curator workflow for those classes follows the same first-class-multi-link policy when the time comes, but uses ULAN/TGN URIs alongside Wikidata.
- **AAT facets are bound per CIDOC class to prevent sense-axis mismatches.** AAT contains many polysemous nouns whose senses live in different facets — e.g. "mosaic" exists as both `mosaic (process)` in the Activities Facet and `mosaics (visual works)` in the Object Types Facet. Cosine matching on the bare token can't disambiguate, so we hard-bind candidate facets per class:
  - **E57_Material** → Materials only.
  - **E22_Human-Made_Object / CACAO_0000023** → Object Types only.
  - **E25_Man-Made_Feature** → Object Types and Physical Attributes (features include patterns, shapes, decorations).
  - **E55_Type** → Object Types, Physical Attributes, Styles & Periods, Materials, Associated Concepts, Activities. E55 genuinely spans facets (an evening dress is an object type, an archaeological excavation is an activity, the Roman period is a style/period); the within-facet sense ambiguity is left to curator review.
  Agents and Brand Names facets are excluded from automatic enrichment — they need different metadata (ULAN, etc.). Within-facet sense mismatches (layer 2: e.g. `collars (horse collars)` matched to a clothing collar) cannot be filtered mechanically and are caught by curator review.
- **Linking density convention**: the curator preferentially links **abstract types** (E55) and **materials** (E57) to KB entries — these are the categories with stable canonical IRIs. Place names (E53) and persons (E21) are linked when the entity has a well-known external referent; minor or local entities are left unlinked. CACAO_0000023 instances rarely carry sameAs (they're often unique to the source). Corpus density per class: E55_Type 54/108, E53_Place 32/49, E21_Person 32/60, E74_Group 19/31, CACAO_0000023 13/45.
- **Wikidata IDs** are normalised to the entity ID form (`http://www.wikidata.org/entity/Qxxxx`); AAT and ICONCLASS follow their canonical IRI schemes.

## URI naming

- Locally-minted URIs use `ex:<role>_<slug>` with a small set of role prefixes:
  - `ex:type_*` for E55_Type nodes (92 in corpus)
  - `ex:feature_*` for E25_Man-Made_Feature (19, fashion)
  - `ex:unit_*` for E58_Measurement_Unit (12)
  - `ex:dim_*` for E54_Dimension (6)
  - `ex:timespan_*` for E52_Time-Span (9)
  - `ex:lang_*` for E56_Language (8, olympic)
  - `ex:material_*` for E57_Material (8, fashion)
  - `ex:visual_*` for E36_Visual_Item (4)
  - `ex:inscription_*`, `ex:letter_*`, `ex:recording_*`, `ex:performance_*`, `ex:collection_*` for the corresponding domain-specific entities.
  - Ungentrified entities (specific objects, persons, places) use direct slugs: `ex:friedrich_weiss`, `ex:cossar_fund`. The role prefixes above are reserved for type/structural/measurement/language nodes.


# Changes after gold consistency review (2026-05-08)

A cross-domain audit surfaced two patterns where the gold disagreed with itself. Both are now uniform.

**E54_Dimension structure unified across the benchmark.** The 15 E54 nodes in the sound domain (sound1, sound2, sound3, sound4, sound5, sound12) previously had only `crm:P90_has_value` plus a label. They now also carry `crm:P91_has_unit` (`ex:unit_wax_cylinder` / `ex:unit_object` / `ex:unit_note` / `ex:unit_pipe` / `ex:unit_row` as appropriate) and `crm:P2_has_type ex:type_count`, matching the pattern fashion already used. The two unlabeled E54s in sound4 (counts of 39 and 47 cylinders) also gained explicit `rdfs:label` strings. The six affected sound files each grew a small "DIMENSION TYPES & UNITS" block declaring the new E55_Type and E58_Measurement_Unit nodes.

**Paired P81+P82 enforced on every E52_Time-Span.** Three time-spans previously violated the paired-bounds rule: `olympic1:timespan_1896` (label-only), `olympic4:timespan_1906` (P82-only with `xsd:gYear`), and `fashion4:timespan_1930s` (label-only). All three now use paired `P81_ongoing_throughout` + `P82_at_some_time_within` with the year-range literal form documented above.

These edits add structure to existing nodes and do not introduce or remove entities.


# Errata / Known Limitations:
- Sound9 and sound10 have the same source text. Sound9 is seen as a factual interpretation, sound10 as a subjective interpretation. Please take this into account when using the benchmark. For that reason, annotations of both sound9 and sound10 were used to create those gold truths.
