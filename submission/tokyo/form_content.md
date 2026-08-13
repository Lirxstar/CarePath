# CP-209 — Submission form draft

> Submission-ready technical wording for CarePath Tokyo. Copy registered team information from the official application account; do not infer member names or team size from the repository. Character limits should be re-checked in the live submission form before final paste.

## One-sentence problem/product statement

**CarePath Tokyo turns an everyday request such as “I need somewhere nearby to cool down” into source-backed Tokyo public-health resources in English, Japanese or Chinese, without requiring the user to know the official service name or upload health records.**

## 1. Identified issue and background

Tokyo publishes valuable public-health and welfare data, but residents and visitors may not know which dataset, agency term or Japanese service name matches their situation. CarePath Tokyo removes this navigation barrier by starting from a natural-language need and location rather than requiring users to understand a government taxonomy.

## 2. Service details

Users open an anonymous web page, choose EN/JA/ZH, describe a need, and use browser location or a manual Tokyo municipality. CarePath maps the request to four bounded categories, runs deterministic geospatial/resource search, and returns ranked cards with provenance, freshness, directions and source-backed contact actions. Urgent language is intercepted first.

## 3. Reasons for technology choices

FastAPI/Pydantic provide an auditable typed boundary, Expo Web provides a responsive public UI, and canonical adapters preserve provenance/freshness. Deterministic filters, distance and ranking keep selection reproducible. A bounded model interface may assist unresolved intent but cannot write facts, coordinates, radius, ranking or safety decisions.

## 4. Use of generative AI and demo URL

Generative AI is bounded to optional structured intent assistance and allow-listed explanation reasons; canonical open data remains the factual authority. Deterministic parsing/search still works if the provider fails. The public build uses a credential-free mock provider for reproducibility, so the primary demo does not depend on a live LLM. Demo: https://carepath-api-8edq.onrender.com/tokyo

## 5. Team capability

Use the registered team/member information exactly as entered in the official account. The build demonstrates capability across AI/ML research, Python backend engineering, typed APIs, open-data ingestion, geospatial search, safety/grounding verification, Expo web delivery, automated evaluation, Docker deployment and CI. Personal affiliations are intentionally omitted from this public repository copy.

## 6. Open-data usage

CarePath Tokyo normalizes five authoritative dataset entries into 13,364 source-backed resources: MHLW hospitals/clinics, Koto Cooling Shelters, and Tokyo family-support and mental-health welfare centres. Returned items retain provenance/freshness. Missing fields remain unknown; the service does not invent live opening, capacity, language or eligibility facts.

## Technical result sentence for slides/form

On the fixed 24-case CP-207 software-engineering suite, CarePath Tokyo passed 24/24 cases with 100% primary scenario completion, intent/tool selection, deterministic geo/ranking, safety-escalation recall, grounded resource-claim precision, provenance presence and language fidelity, with 0 unsupported factual resource claims. These are reproducibility and software-acceptance results, not clinical validation or real-world effectiveness evidence.

## Registered-team fields that must be copied manually

- Registered team name
- Registered member count
- Registered member names/roles, if the submission form asks for them
- Any organizer-specific participant ID or Slack/team identifier

Do not derive these values from Git history or repository ownership.
