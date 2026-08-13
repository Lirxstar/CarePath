# CP-207 — Tokyo evaluation and end-to-end acceptance

## Scope

CP-207 is a reproducible software-engineering acceptance suite for CarePath Tokyo. It evaluates multilingual intent routing, deterministic geospatial/resource selection, source grounding, failure handling, safety escalation and browser usability. It does **not** claim clinical validation, diagnostic accuracy or real-world health effectiveness.

The suite reuses the frozen CP-202 journeys and the CP-203 through CP-206 implementation rather than creating a separate demo path.

## Fixed evaluation set

`evaluation/tokyo/scenarios.json` is version controlled and currently contains 24 cases:

- all 9 frozen CP-202 primary EN/JA/ZH journeys;
- EN/JA/ZH paraphrases for healthcare and mental-health support;
- ambiguous and unsupported requests;
- hard-constraint no-match behaviour;
- explicit partial and stale source-data cases;
- model-unavailable fallback;
- prompt-injection resistance;
- EN/JA/ZH emergency escalation;
- the denied-browser-location/manual-fallback browser contract.

Each API case records expected status, intent/category where applicable, location, expected deterministic resource ordering, safety disposition and any special grounding expectation such as fields that must remain unknown or freshness that must remain stale.

## Deterministic fixture and provider boundary

The evaluator executes the real `POST /tokyo/agent/search` route against a small fixed source-backed `TokyoResourceRepository`. Every fixture resource has canonical provenance. Some records deliberately contain unknown fields or stale freshness so the evaluator can verify that missing/stale facts are not converted into positive/current claims.

The evaluation provider is deliberately unavailable. This has two purposes:

1. CI never requires a paid or secret model credential.
2. The final product path must remain functional when explanation generation is unavailable.

CP-204's existing structured-provider tests remain responsible for valid model-assisted parsing, invalid structured output, allow-list enforcement and fabricated-explanation rejection. CP-207 runs those tests as regressions and adds final product-path metrics rather than pretending a scripted provider is a model-quality benchmark.

## Metrics and thresholds

The fixed run reports:

- primary scenario completion;
- intent/tool-selection accuracy;
- deterministic geo/ranking correctness;
- safety-escalation recall;
- grounded resource-claim precision;
- unsupported factual resource claims;
- provenance presence;
- interface-language fidelity.

Frozen engineering thresholds are stored beside the cases. The current acceptance boundary requires:

- primary scenario completion: 100%;
- deterministic geo/ranking correctness: 100%;
- safety-escalation recall: 100%;
- unsupported factual resource claims: 0;
- provenance presence: 100%;
- intent/tool selection: at least 90%;
- language fidelity: 100%.

These thresholds are software acceptance criteria only.

## Reproduction

From the repository root after installing the development dependencies:

```bash
python -m backend.evaluation.tokyo_cli \
  --scenarios evaluation/tokyo/scenarios.json \
  --output-dir evaluation/tokyo/results
```

The command writes:

- `results.json` — complete per-case outcomes, including failures rather than only successful examples;
- `summary.md` — concise metrics and any failed case IDs/reasons.

It exits non-zero if a frozen threshold fails. The scenario SHA-256 is included in the report, and the report contains no runtime timestamp, so the same versioned inputs produce the same machine-readable result.

## Browser acceptance

The dedicated `CP-207 Tokyo evaluation` workflow also starts the integrated production-style Docker deployment and runs `apps/mobile/e2e/tokyo_web.spec.ts` with Playwright. That existing CP-206 spec provides final desktop/mobile browser coverage for:

- direct `/tokyo` entry;
- source/freshness visibility;
- EN/JA/ZH interface switching;
- denied geolocation followed by manual municipality fallback on a mobile viewport;
- direct-route refresh;
- emergency safety boundary before ordinary results;
- return to the unchanged CarePath Core experience.

Both machine-readable evaluation output and browser evidence are uploaded as CI artifacts, including failure evidence when a gate does not pass.
