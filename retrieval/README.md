# Retrieval

Shared retrieval boundary for personal and external evidence namespaces.

## Guideline ingestion pipeline

The ingestion workflow converts approved external guideline sources into auditable chunks:

1. Load `data/guidelines/sources.yaml`.
2. Import HTML, Markdown, text, or permitted PDF text.
3. Apply licence gate before storing content.
4. Remove navigation, repeated headers/footers, and empty boilerplate.
5. Split by heading and semantic boundaries.
6. Store chunk provenance metadata.

Each chunk must retain:

- source_id
- chunk_id
- title
- section
- URL
- publication/update date
- retrieval date

Sources marked `metadata_only_pending_ai_permission` are stored as provenance records only and must not enter the text chunk store.

## Dual retrieval

CP-007 implements the executable retrieval contract in `backend/retrieval/dual.py`.

- Personal records and external guideline chunks use separate namespace-bound stores.
- Personal retrieval requires `user_id` and excludes other users before ranking.
- Personal evidence IDs are derived from existing record IDs.
- External evidence IDs reuse the canonical CP-006 `chunk_id` and preserve `source_id`.
- `DualRetriever` returns personal and external hits in separate channels.
- The initial deterministic Recall@5 fixture is `data/evaluation/cp007_retrieval_cases.json`.

See `docs/cp007_dual_retrieval.md` for the contract, evaluation method, and limitations.
