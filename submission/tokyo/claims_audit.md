# CP-209 submission claims audit

All public-facing submission materials should use only the claims below unless the implementation/evidence is updated and this audit is revised.

| Claim | Status | Implementation / evidence |
| --- | --- | --- |
| Anonymous `/tokyo` public web route | Supported | CP-208 exact public Render acceptance |
| EN/JA/ZH interface and journeys | Supported | CP-206/CP-207/CP-208 Playwright contracts |
| Browser coordinates or manual Tokyo municipality | Supported | Tokyo web/API contract |
| No account or health-file upload required for Tokyo primary journey | Supported | CP-208 public product boundary |
| Four bounded navigation categories | Supported | `docs/tokyo_scope.md` and CP-204 intent allow-list |
| Five authoritative dataset entries | Supported | `data/tokyo/sources.json` |
| 13,364 normalized public resources in accepted deployment | Supported | exact CP-208 public verification for `c33cf0f51f5da402a0db400433719baf506cb942` |
| Resource facts retain provenance/freshness | Supported | CP-201 resource contract and CP-208 verifier |
| Deterministic geo/resource ranking | Supported | CP-203 and CP-207 evaluation |
| Safety triage runs before ordinary ranking | Supported | CP-205 |
| Precise coordinates/free-text are not durably stored by Tokyo routes | Supported | CP-205 privacy contract |
| Provider failure can fall back to deterministic supported navigation | Supported | CP-204/CP-208 |
| Public deployment uses a live generative-AI model | **Not supported** | `render.yaml` configures `CAREPATH_LLM_PROVIDER=mock` |
| A real model is required for the primary demo | **False** | deterministic primary flow is intentionally provider-independent |
| CP-207 passed 24/24 cases | Supported | CP-207 evaluation artifact `9174326086` |
| Primary completion / intent / ranking / safety / grounding / provenance / language metrics are 100% | Supported as software acceptance | CP-207 evaluation artifact |
| Unsupported factual resource claims = 0 | Supported as software acceptance | CP-207 evaluation artifact |
| Clinically validated / medically effective / improves health outcomes | **Do not claim** | no clinical study or real-world outcome evaluation |
| Facility is open now / has live capacity / accepts patients now | **Do not claim** unless a future live source supports it | static source-bound product contract |
| Unknown language support, eligibility or accessibility is positive | **Do not claim** | unknown fields remain unknown |

## Generative-AI wording that is safe to use

“CarePath Tokyo has a bounded, replaceable model-provider layer for structured intent assistance and allow-listed explanation reasons. The model is not the factual authority: canonical open data and deterministic tools control resource facts, location, radius, filters, ranking and provenance. The current public submission build uses a credential-free mock provider, so the primary demonstration is reproducible without a live LLM.”

## Evaluation wording that is safe to use

“On the fixed 24-case CP-207 software-engineering suite, the submitted implementation passed all cases and met its frozen engineering thresholds, including 100% multilingual primary completion, deterministic ranking, safety escalation, grounded resource-claim precision, provenance and language fidelity, with zero unsupported factual resource claims. These results do not establish clinical effectiveness or real-world health outcomes.”
