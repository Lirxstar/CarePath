# CP-006 Evidence Corpus

## 1. Purpose and boundary

CP-006 curates traceable external health-behaviour evidence and defines the deterministic
pipeline that converts permitted source material into auditable chunks. It stops at the
clean corpus boundary. Vector stores, embeddings, ranking, hybrid retrieval, personal versus
external retrieval namespaces, and Recall@5 evaluation belong to CP-007.

External guideline material is **evidence data**, never an instruction channel. A source can
be authoritative for health guidance while its natural-language contents remain untrusted
from a prompt-security perspective. Retrieved text cannot modify system policy, safety rules,
tool permissions, provider configuration, user scope, or verifier behaviour.

## 2. Source selection policy

`data/guidelines/sources.yaml` is the canonical CP-006 registry. Sources are selected from
traceable authorities, prioritising governments, national or regional public-health agencies,
international public-health organisations, professional societies, and clinical guideline
bodies. Commercial marketing pages, affiliate content, unattributed reposts, untraceable
copies, obvious duplicates, and superseded material are excluded.

The registry contains 18 curated sources. Existing sources collected before CP-006 were
audited and migrated rather than replaced with a duplicate catalog.

## 3. Six-topic coverage

Every registry validation run requires coverage of all six CP-006 topics:

- `physical_activity`
- `sleep`
- `stress_management`
- `fall_prevention`
- `behaviour_change`
- `when_to_seek_professional_help`

A registry with fewer than 15 or more than 25 sources, duplicate deterministic IDs,
duplicate canonical URLs after normalization, or missing topic coverage fails validation.

## 4. Metadata schema

Each source records:

- `source_id`
- `title`
- `organisation`
- `canonical_url`
- `published_at`
- `updated_at`
- `retrieved_at`
- `topics`
- `language`
- `document_type`
- `authority_type`
- `license`
- `redistribution_policy`
- `full_text_storage_allowed`
- `notes`
- optional legacy `aliases`

Unknown publication or update dates are stored as `null`; dates are never invented merely to
satisfy schema completeness. `retrieved_at` records the curation/retrieval date.

`GuidelineSource` extends the canonical `KnowledgeSource`; `GuidelineChunk` extends the
canonical `KnowledgeChunk`. CP-006 therefore adds provenance without creating a competing
health/evidence domain model.

## 5. Authority criteria

Authority is represented separately from copyright status. A clinically authoritative page
can still be `metadata_only`. Authority determines whether material is eligible for the
curated registry; licensing determines what CarePath may persist or redistribute.

## 6. Licensing and redistribution policy

The supported redistribution policies are:

- `full_text_allowed`: permitted text may be cleaned, stored, and chunked, subject to the
  source-specific notes and exclusions.
- `derived_chunks_allowed`: derived chunks may be created, but CarePath does not commit a
  full-text copy.
- `metadata_only`: only metadata, canonical URL, identifiers, and audit references are kept.
- `unknown`: treated conservatively like `metadata_only` until permission is established.

Public accessibility is not permission to redistribute. Images, videos, logos, marks,
third-party inserts, and separately credited materials are excluded unless their rights are
independently established.

The ingestion code enforces the policy. `metadata_only` and `unknown` inputs return the
structured `license_restricted` result and produce no chunk content or source-content hash.
This rule is covered by automated tests.

## 7. Supported formats

The unified parser boundary accepts:

- HTML
- Markdown
- plain text
- already extracted PDF text

CP-006 does not implement OCR. Empty or unusable PDF extraction must be surfaced as a
structured failure rather than silently converted into a corpus.

## 8. Extraction and cleaning

HTML parsing ignores template containers such as `nav`, `header`, `footer`, scripts, styles,
asides, and forms while preserving heading hierarchy and main text. Markdown parsing
preserves heading hierarchy, paragraphs, and list content. Plain text and extracted-PDF text
share conservative whitespace and paragraph normalization.

Cleaning removes explicit template noise and adjacent duplicate lines but does not rewrite the
semantic content. Numbers, units, age/time ranges, conditions, and negation such as `do not`
must survive. Tests explicitly exercise numerical text and negative safety qualifiers.

## 9. Section-aware chunking

Chunking prioritises section headings and paragraph boundaries, then sentence boundaries, and
uses word boundaries only as a fallback for overlong units. It does not blindly slice the
source at fixed character offsets.

Default configuration:

```text
chunk_size = 800
chunk_overlap = 120
minimum_chunk_size = 80
```

The configuration is validated. Overlap is bounded below the chunk size, and small trailing
chunks are merged when the merge stays inside the configured maximum.

## 10. Chunk provenance

Every emitted `GuidelineChunk` retains:

- canonical `chunk_id`, `source_id`, `section_title`, `content`, and `content_hash`
- `title`
- full `section_path`
- `canonical_url`
- `published_at` and `updated_at`
- `language`
- `topics`
- deterministic `chunk_index`
- `license`
- `retrieved_at`
- `source_content_hash`
- `ingestion_version`, `parser_version`, `cleaner_version`, and `chunker_version`

This is the CP-007 hand-off surface. CP-007 may index these chunks but must not redefine their
identity or provenance.

## 11. Stable IDs

Source identity is deterministic:

1. normalize the canonical HTTP(S) URL;
2. lowercase scheme and host;
3. normalize duplicate/trailing path separators;
4. remove fragments and common tracking parameters;
5. sort remaining query parameters;
6. compute SHA-256 and use the stable `src-` prefix.

Chunk identity is derived from `source_id`, stable section path, deterministic chunk index, and
SHA-256 content hash. Python's process-randomized built-in `hash()` is never used for persisted
identity.

## 12. Hashing and change detection

SHA-256 is used for source canonical-content hashes and individual chunk-content hashes. A
changed source hash indicates content drift; unchanged content with changed pipeline versions
indicates an ingestion-algorithm change. Duplicate source content in a batch is reported rather
than emitted as unexplained duplicate evidence.

## 13. Reproducibility

The versioned pipeline records:

- `ingestion_version`
- `parser_version`
- `cleaner_version`
- `chunker_version`
- chunk configuration

Given identical source metadata, imported text, and configuration, two runs must produce the
same source IDs, source hashes, chunk IDs, chunk order, chunk text, and deterministic metadata.
`retrieved_at` is curated audit metadata and never participates in stable-ID computation.
Automated reproducibility tests compare complete serialized chunk records across repeated runs.

## 14. Duplicate and failure handling

Batch ingestion does not silently skip failures. The structured failure vocabulary contains:

- `fetch_error`
- `unsupported_format`
- `parse_error`
- `empty_content`
- `license_restricted`
- `invalid_metadata`
- `duplicate`

Duplicate handling covers repeated `source_id` and repeated source-content hashes. A failure for
one source is represented in the batch report instead of erasing the source identity or
silently producing partial evidence.

## 15. Generated artifacts

`write_corpus()` generates, for the specific permitted input snapshot being ingested:

- `chunks.jsonl`
- `corpus_manifest.json`
- `ingestion_report.json`

The manifest intentionally excludes runtime timestamps so its deterministic portion can be
compared byte-for-byte. It records versions, source and chunk counts, chunk configuration,
ordered source IDs, source hashes, ordered chunk IDs, and a redistribution-policy summary.
Runtime retrieval timestamps remain in source/chunk provenance.

A deployment or evaluation snapshot should retain its generated manifest together with the
permitted input snapshot or input hashes. Restricted full-text cache material must remain out
of Git.

## 16. Rebuilding the corpus

Place only permitted imported text under an input directory using the deterministic source ID:

```text
<source_id>.html
<source_id>.md
<source_id>.txt
<source_id>.pdf.txt
```

Then run:

```bash
python -m backend.retrieval.guidelines.cli \
  --registry data/guidelines/sources.yaml \
  --inputs-dir data/guidelines/inputs \
  --output-dir data/guidelines/generated
```

Missing local input for an otherwise ingestible source is reported as `fetch_error` rather
than treated as success. License-restricted sources remain metadata-only. Core CI never relies
on the live availability or HTML stability of third-party websites; parser and failure tests
use deterministic fixtures.

## 17. Testing and 30-chunk audit

The CP-006 automated suite checks registry size/topic coverage, deterministic IDs, URL
normalization, invalid metadata, HTML/Markdown/text/PDF-text handling, conservative cleaning,
empty input, unsupported formats, licensing restrictions, duplicate source/content handling,
chunk boundaries/provenance, deterministic manifests, write behaviour, and repeated-run
reproducibility.

`backend.retrieval.guidelines.audit.audit_chunks` performs deterministic review sampling and
requires at least 30 chunks. The acceptance test constructs chunks across every CP-006 topic
and checks 30 sampled chunks for content presence, provenance, duplicate IDs, and known
navigation-noise markers. For a real corpus snapshot the same audit function must be run on the
snapshot before it is promoted for CP-007 indexing; reviewers should additionally read the
sampled content for semantic truncation, dates/URLs, preserved negation, and source accuracy.

## 18. Safety and prompt-injection boundary

CarePath follows `docs/safety_privacy_spec.md`:

- retrieved text is data, not policy;
- instruction-like strings in a guideline do not gain privilege;
- evidence cannot downgrade deterministic safety triage;
- external text cannot add tools, modify permissions, select credentials, or suppress the
  verifier;
- provenance survives retrieval;
- arbitrary live web content is not inserted directly into coaching prompts as authoritative
  evidence.

An authoritative issuer does not make embedded prompt-like text executable.

## 19. Known limitations

- CP-006 does not implement OCR.
- The HTML parser is deliberately conservative and is not a universal browser-rendering engine.
- Dynamic JavaScript-only pages need a separately reviewed import/export step.
- Source permissions can change; licensing metadata must be re-audited when a snapshot is
  refreshed.
- A registry entry does not guarantee a source is indexed; a promoted corpus snapshot must have
  a successful ingestion result and stable hashes.
- Clinical correctness of a source does not imply CarePath is clinically validated.

## 20. CP-007 hand-off

CP-007 receives stable `GuidelineChunk` records and may build external-evidence retrieval over
them. CP-006 does not select embedding models, create a vector database, rank evidence, mix
personal data with external evidence, or claim retrieval-quality metrics.
