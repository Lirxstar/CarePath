# CP-007 Dual Retrieval

## Purpose

CP-007 keeps personal evidence and curated external guideline evidence in separate trust domains while providing two retrieval implementations:

- the original deterministic `InMemoryRetrievalStore`, retained as a small lexical baseline and compatibility seam;
- the versioned Qdrant external-evidence index and database-backed Patient Evidence service used for the complete retrieval acceptance surface.

External evidence always reuses CP-006 source/chunk identity. Personal evidence always remains scoped to a single `user_id` before ranking or summarisation.

## External guideline vector index

`backend.retrieval.vector.QdrantExternalEvidenceIndex` stores CP-006 `GuidelineChunk` records in Qdrant using cosine similarity. Local development uses Qdrant Local (`QdrantClient(path=...)`); no external vector service is required.

The index contract is versioned as `cp007-vector-v1` and the default collection is:

```text
carepath_guidelines_cp007_v1
```

The production embedding seam defaults to the multilingual FastEmbed model:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

`DeterministicHashEmbeddingModel` exists only for deterministic CI/tests and must not be presented as the production semantic embedding model.

### Collection payload schema

Every indexed point preserves:

- `chunk_id` and `source_id`;
- title, section title and full section path;
- canonical URL;
- published/update/retrieval dates;
- language and topics;
- organisation;
- licence;
- source/content hashes;
- CP-006 ingestion version;
- embedding model and vector-index version;
- chunk content and a display-ready citation.

Filterable fields are declared by `COLLECTION_SCHEMA`: topic, language, organisation and update date, in addition to stable identity/provenance fields.

### Rebuild command

First build/promote the permitted CP-006 corpus snapshot so that `chunks.jsonl` exists. Then rebuild the vector index with one command:

```bash
carepath-index \
  --chunks data/guidelines/generated/chunks.jsonl \
  --registry data/guidelines/sources.yaml \
  --qdrant-path data/guidelines/qdrant
```

Equivalent module invocation:

```bash
python -m backend.retrieval.vector_cli \
  --chunks data/guidelines/generated/chunks.jsonl \
  --registry data/guidelines/sources.yaml \
  --qdrant-path data/guidelines/qdrant
```

The command deletes/recreates only the configured versioned collection, embeds the ordered CP-006 chunks and prints an `IndexBuildReport` containing collection name, index version, embedding model/vector size, source count and chunk count.

### Search API

```text
GET /evidence/external/search
```

Supported query controls:

- `query`;
- `top_k`;
- repeated `topics` filters;
- `language`;
- exact normalised `organisation`;
- `updated_from` / `updated_to`.

Each response item contains the ranked score, chunk content, complete retrieval metadata and a citation containing title, organisation, section, source date and canonical URL.

## Patient Evidence

`backend.retrieval.patient.PatientEvidenceService` builds a separate user-scoped evidence channel from persisted profiles, observations, journals, goals and historical plans.

```text
GET /evidence/patient/search
```

Supported controls:

- strict `user_id`;
- recent 7-day or 30-day window;
- explicit timezone-aware `start_at` / `end_at` range, bounded to 366 days;
- metric-type filters;
- keyword retrieval over journal, goal and plan/action text.

Every database query includes the requested user scope. Other users never enter the candidate set.

### Analytics-first structured evidence

Raw longitudinal observations are not copied into the LLM context as a long list. Numeric series are summarised through existing CP-005 deterministic analytics (`compute_trend`) and emit:

- metric and unit;
- window dates;
- usable/expected sample counts;
- mean and slope;
- CP-005 reliability;
- source observation IDs.

Boolean event metrics are similarly reduced to bounded event counts plus reliability and source IDs.

Text journals are explicitly labelled `subjective_description`. Deterministic time-series summaries are labelled `structured_fact`; profile/goals/plans use `context_record`. This prevents a self-reported description from being represented as a measured fact.

## Stable evidence identity

The legacy retrieval contract remains compatible:

```text
personal:<record_type>:<record_id>
external:<chunk_id>
```

The Qdrant backend preserves the canonical CP-006 `chunk_id` as the external identity while using a deterministic UUIDv5 only as Qdrant's internal point ID.

## Recall@5 evaluation

The original lexical fixture remains at:

```text
data/evaluation/cp007_retrieval_cases.json
```

The vector acceptance fixture is:

```text
data/evaluation/cp007_vector_retrieval_cases.json
```

It contains 12 labelled external queries covering all six CP-006 topics. `external_recall_at_k(..., k=5)` computes macro Recall@5 from retrieved canonical chunk IDs. CI uses a deterministic embedding seam so retrieval quality tests do not depend on network/model downloads; production index builds use the configured multilingual model.

Focused tests:

```bash
pytest tests/test_vector_retrieval.py tests/storage/test_patient_evidence.py tests/test_evidence_api.py -q
```

## Safety and trust boundary

External retrieved text is evidence data, never executable policy. It cannot alter system rules, safety triage, tool permissions, provider settings or verifier behaviour. Patient Evidence remains a separate channel with record references and reliability labels so downstream Planner/Verifier components can distinguish measured summaries, user descriptions and guideline claims.
