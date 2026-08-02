# Fixed evaluation suite

CP-016 defines the version-controlled evaluation inputs used by later baseline and metric work.

## Contract

`evaluation/scenarios/` contains exactly 48 synthetic engineering scenarios:

| Category | Count |
|---|---:|
| Routine coaching | 16 |
| Longitudinal trends | 8 |
| Missing or conflicting data | 8 |
| Safety escalation | 8 |
| Prompt injection or hostile documents | 4 |
| Multilingual across English, Chinese, and Japanese | 4 |

Every scenario records:

- the synthetic persona and user question;
- the expected deterministic tools;
- personal and external evidence references;
- expected findings;
- the expected safety and security outcome;
- prohibited claims or behaviours;
- the required response language.

The cases are fixed synthetic tests. They are not clinical validation cases and must not be described as evidence of clinical effectiveness.

## Files

- `scenarios/index.json` defines the suite identity, required counts, and category files.
- `scenarios/routine_coaching.json` contains 16 routine planning cases.
- `scenarios/longitudinal_trends.json` contains 8 time-series cases.
- `scenarios/missing_or_conflicting_data.json` contains 8 uncertainty cases.
- `scenarios/safety_escalation.json` contains 8 caution or urgent cases.
- `scenarios/hostile_documents.json` contains 4 prompt-injection cases.
- `scenarios/multilingual.json` contains 4 English, Chinese, and Japanese cases.

## Validate

From the repository root:

```bash
python -m backend.evaluation.scenarios
pytest tests/test_cp016_evaluation_set.py
```

The validator rejects incorrect counts, duplicate identifiers, missing tool coverage, malformed evidence references, routine outcomes for safety cases, hostile documents without injection controls, and incomplete multilingual coverage.

## Relationship to later work

CP-016 defines inputs and expected annotations only. CP-017 will execute B0–B3 through one evaluation interface and calculate the frozen retrieval, grounding, tool, safety, and latency measures.
