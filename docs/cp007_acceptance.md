# CP-007 Acceptance Mapping

- Separate personal/external stores or namespaces: implemented by `RetrievalNamespace` and namespace-bound `InMemoryRetrievalStore`.
- Stable evidence identifiers: personal hits derive from existing record IDs; external hits reuse canonical CP-006 `chunk_id` and preserve `source_id`.
- Retrieval tests: `tests/test_dual_retrieval.py` covers namespace separation, user isolation, stable identities, duplicate rejection, dual-channel retrieval, and invalid inputs.
- Initial Recall@5 evaluation: `data/evaluation/cp007_retrieval_cases.json` is evaluated by `recall_at_k`; the focused test requires macro Recall@5 = 1.0.

The deterministic lexical scorer is a prototype baseline. The namespace and evidence-ID contract is intended to remain stable if a later vector or hybrid store replaces it.
