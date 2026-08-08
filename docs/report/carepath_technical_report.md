# CarePath: Evidence-Grounded Adaptive Health Coaching from Longitudinal Data

## Technical report

CarePath is a research prototype for adaptive health-behaviour coaching from longitudinal synthetic data. The project addresses a practical limitation of generic conversational assistants: a single user message does not reliably encode recent trends, longer-term baselines, data quality, past plans, or whether earlier recommendations were feasible. CarePath therefore treats coaching as a bounded software workflow rather than a single free-form model call.

The implemented system combines four elements. First, deterministic time-series tools calculate trends, window comparisons, change signals, missingness and adherence from validated observations. Second, personal context and external public guidance are retrieved through separate evidence paths so user facts and guideline evidence remain distinguishable. Third, a bounded agent workflow performs Safety Triage, Context Builder, Tool Router, Planner, Grounding & Safety Verifier, and Response Composer stages. Fourth, a React Native / Expo client exposes Today, Coach, Health Data, and Plan & History views, including explicit feedback that can modify later plans.

The central engineering claim is not that the prototype is clinically effective. It is that a health-behaviour assistant can be made more auditable by moving numerical analysis, evidence retrieval, safety escalation, and state transitions into explicit software components around the language-model boundary. Model output is treated as an untrusted draft. The model endpoint has no direct database access, deterministic safety logic cannot be downgraded by the model, and external documents are treated as data rather than instructions.

A fixed 48-scenario synthetic evaluation suite exercises routine coaching, longitudinal trends, missing/conflicting data, safety escalation, hostile-document or prompt-injection cases, and multilingual cases. On the recorded complete-workflow reference run, citation precision was 1.00, evidence-supported claim rate 1.00, unsupported-claim rate 0.00, contradiction rate 0.00, safety-escalation recall 1.00, prompt-injection resistance 1.00, and runner failure rate 0.00. Lower-scoring non-safety metrics are retained in the report rather than hidden: Recall@5 was 0.8295, gold-evidence coverage 0.7798, patient-context fidelity 0.7045, and tool-selection accuracy 0.7909.

The reviewer deployment packages Expo Web and FastAPI in one production Docker image, with PostgreSQL as the persistence service. The public demo uses a deterministic mock model provider for reproducibility and should be read as a software-engineering demonstration, not a clinical validation study.

<!-- PAGE BREAK -->

# 1. System design and bounded orchestration

A routine request enters FastAPI, where schema validation, request IDs, error contracts, and service boundaries are enforced before any agent stage runs. Safety Triage is intentionally deterministic. It can route a request to a caution or urgent/blocked disposition before ordinary planning, preventing a generative model from deciding whether a red-flag condition should be ignored. Routine requests continue to Context Builder, which reads only task-relevant user-scoped state rather than exposing the model to a raw database or unrestricted history.

Tool Router then selects validated, allow-listed capabilities under a bounded call budget. Structured time-series questions are delegated to deterministic analysis tools. These tools calculate 7/30-day comparisons, trend direction, change detection, missingness/data quality, and adherence summaries from stored observation references. This design avoids asking the language model to infer numerical relationships from long unstructured arrays.

Evidence is separated into two namespaces. Personal Context Retriever returns minimal facts or snippets tied to the active user/persona and stable record references. External Evidence Retriever returns curated public-guidance chunks with source and provenance metadata. The separation matters because the verifier can distinguish a claim about the user's own history from a general guideline claim. External text never gains policy or tool authority merely because it appears in a retrieved chunk.

Planner receives the bounded context, deterministic tool results, retrieved evidence, goals, preferences, previous plans, and feedback. Its output is a small structured seven-day draft rather than an unconstrained action sequence. Grounding & Safety Verifier checks whether evidence-requiring statements are supported, citations align with the claims they accompany, user facts are consistent with referenced records, safety requirements are preserved, and prohibited diagnostic or medication-change language is absent. A failed draft can be rewritten once; repeated failure degrades to a controlled safe response instead of entering an open-ended correction loop.

Response Composer renders a stable user-facing structure with observations, evidence interpretation, a realistic weekly plan, professional-help guidance, sources, and uncertainty. Explicit accept/reject/modify/complete feedback is persisted and becomes an input to later planning. This closes the adaptation loop: the system is not limited to a one-shot answer, and repeated difficulty with an action can result in a smaller subsequent plan.

The inference boundary remains replaceable through ModelProvider. A provider receives only a sanitized task-specific request and returns a normalized untrusted completion or structured draft. Database credentials, raw persistence access, hidden policy, and unrestricted external text are not delegated to the endpoint.

<!-- PAGE BREAK -->

# 2. Data, evidence, client, and deployment

The persistence layer models user profiles, observations, journal entries, goals, intervention plans, plan feedback, and audit events. SQLAlchemy repositories and services isolate API code from direct SQL, while Alembic provides migration control. SQLite supports local development and PostgreSQL is used by the containerized reviewer deployment. Import paths validate project CSV/JSON packages and a deliberately bounded FHIR subset rather than claiming full FHIR-server conformance.

Synthetic data generation supplies reproducible 30–60 day longitudinal scenarios without introducing patient privacy risk. Personas can include sleep, steps/activity, resting heart rate, stress or mood, journals, goals, missingness, noise, periodicity, and injected events. The same seed reproduces the same synthetic package. This provides controlled ground truth for engineering tests while keeping the project outside real-patient research.

The external evidence pipeline curates public health and behavioural guidance with source identity, organisation, URL, dates, topic, language, licence/use notes, hashes, stable IDs, and provenance. Ingestion cleans and chunks documents for retrieval while preserving traceability. Personal evidence and external evidence remain separate in retrieval and in downstream evaluation. This separation supports citation checking and helps prevent a retrieved external statement from being mistaken for a fact about the user.

The Expo application exposes four reviewer-facing routes. Today presents connection state, recent summaries, baseline comparison, and the current action. Health Data exposes raw longitudinal charts, date windows, missingness, suspect records, and import reports. Coach sends a bounded coaching request and renders the structured response plus personal and external evidence. Plan & History exposes the current seven-day plan and feedback controls, allowing a reviewer to choose a lighter action and then observe a changed follow-up recommendation.

The production Dockerfile uses a Node build stage to export Expo Web and a Python runtime stage for FastAPI. FastAPI serves the reviewer HTML and static assets at the same origin as API routes, so the browser uses relative requests and does not depend on a second frontend service or permissive cross-origin configuration. PostgreSQL is a separate service. Container startup applies Alembic migrations before Uvicorn. `/health/live` checks process liveness; `/health/ready` requires the configured database and model provider to be healthy.

The public reviewer is deployed on a free demo tier and uses the deterministic mock provider. The hosting tier may cold-start after inactivity and the free managed database is not a durable production datastore. These constraints are documented so reviewer convenience is not confused with production readiness.

<!-- PAGE BREAK -->

# 3. Evaluation and safety results

The formal evaluation set contains 48 fixed scenarios: 16 routine coaching cases, 8 longitudinal-trend cases, 8 missing/conflicting-data cases, 8 safety-escalation cases, 4 hostile-document/prompt-injection cases, and 4 multilingual cases. The scenarios and expected annotations are version controlled so the same inputs can be rerun across baselines. Four system configurations are compared under a shared contract: a model-only baseline, an external-guideline retrieval baseline, a dual personal/external retrieval baseline, and the complete production workflow.

The reference complete-workflow measurements are shown below. They are synthetic software-engineering measurements and do not estimate clinical benefit.

| Metric | Reference result |
| --- | ---: |
| Recall@5 | 0.8295 |
| MRR | 0.9394 |
| Gold evidence coverage | 0.7798 |
| Citation precision | 1.0000 |
| Evidence-supported claim rate | 1.0000 |
| Patient-context fidelity | 0.7045 |
| Tool-selection accuracy | 0.7909 |
| Tool success | 1.0000 |
| Unsupported claim rate | 0.0000 |
| Contradiction rate | 0.0000 |
| Safety-escalation recall | 1.0000 |
| Prompt-injection resistance | 1.0000 |
| Runner failure rate | 0.0000 |

The results support several bounded conclusions. The reference workflow successfully preserved citation support and avoided measured unsupported claims in the fixed suite. Safety escalation and hostile-document resistance also passed all applicable reference cases. Deterministic tool execution itself was reliable in the measured run. At the same time, patient-context fidelity and tool-selection accuracy remain below stronger research targets, and retrieval gold-evidence coverage is not complete. These values are visible because the evaluation is intended to identify limitations as well as demonstrate successful cases.

The safety model is layered rather than purely generative. Deterministic triage handles red-flag routing. Tool arguments validate date ranges, metric names, user IDs, and call limits. Personal retrieval is user-scoped. External documents retain provenance and are explicitly untrusted as instructions. Verifier checks support, citations, user-fact consistency, unsafe certainty, and required escalation language. A single rewrite limit prevents verifier/planner loops from becoming unbounded.

CI makes these claims reproducible at the software level. Repository quality gates run formatting, linting, type checks, Python tests, frontend checks, Expo exports, and coverage. Dedicated evaluation/red-team workflows rerun the fixed scenario contract. Deployment workflows build the production image, start PostgreSQL and the API, verify migrations and health endpoints, and execute the recorded reviewer browser journey.

<!-- PAGE BREAK -->

# 4. Reproducibility, limitations, and conclusion

A clean clone can launch the reviewer-equivalent local stack with one command:

`docker compose --env-file deployment/.env.compose.example up -d --build --wait`

The command builds the same integrated Expo Web + FastAPI production image used by the reviewer deployment and starts PostgreSQL. The CP-021 clean-room workflow executes this exact command on a fresh hosted runner, confirms that `/` is the Expo Web document, checks `/health/live`, `/health/ready`, and `/openapi.json`, verifies the Alembic migration head, and tears the stack down. CP-020 separately runs the same primary browser journey against an integrated Docker stack and the real public reviewer origin.

The prototype has deliberate limitations. It is not a medical service, diagnostic system, clinical-risk predictor, treatment recommender, emergency service, or medical device. It does not recommend medication initiation, cessation, or dose changes. It uses synthetic or openly licensed data and has not recruited real patients. Consequently it makes no claim of clinical efficacy, feasibility, acceptability, generalisation to real populations, or regulatory readiness.

The core system also does not implement full FHIR conformance, live electronic-health-record or commercial-wearable integrations, medical imaging or physiological-signal interpretation, model training/fine-tuning, reinforcement learning, unconstrained autonomous action, clinician dashboards, telemedicine, penetration-tested production security, or 24/7 service guarantees. The public deployment is a reviewer demo using a mock provider and free infrastructure rather than a production service-level architecture.

Within those limits, CarePath demonstrates a complete engineering pattern for trustworthy tool-using AI: longitudinal state is summarized by deterministic code; user and guideline evidence are separately retrievable and traceable; generative planning is bounded by typed tools and explicit state; safety escalation is not delegated to model discretion; model drafts are verified before release; feedback changes later planning; and the same system is exercised through automated evaluation, container deployment, and a reviewer-facing client.

The most important remaining research direction is therefore not adding more autonomous behaviour. It is improving the weaker measured components while retaining the safety and traceability invariants: higher personal-context fidelity, more accurate tool selection, better evidence coverage, and evaluation on appropriately governed real-world or prospective data if such work is later approved. The current prototype provides a reproducible foundation for that research without presenting synthetic benchmark success as clinical validation.
