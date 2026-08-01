# CarePath Agent — Initial Issue Board

This backlog implements the frozen scope in `PROJECT_SCOPE.md`. The order below is dependency-aware. Issue IDs are stable planning identifiers until corresponding GitHub issues are created.

## Board policy

- Work-in-progress limit: **2**.
- An issue enters **Ready** only when acceptance criteria are testable.
- `B-core` issues always take precedence over hackathon extensions.
- AMD and Tokyo work may not begin when a P0 B issue is blocked or incomplete.

## Ready

### CP-001 — Initialise repository and quality gates
**Labels:** `B-core`, `documentation`, `P0-application-blocking`  
**Acceptance criteria:**
- canonical directory structure exists;
- `PROJECT_SCOPE.md` is committed at repository root;
- formatter, linter and test commands are documented;
- secrets and generated health data are excluded appropriately.

### CP-002 — Implement canonical domain models
**Labels:** `B-core`, `data`, `backend`, `P0-application-blocking`  
**Depends on:** CP-001  
**Acceptance criteria:**
- Pydantic and persistence models exist for all core entities;
- enum vocabularies match the frozen scope;
- validation tests cover invalid units, unsupported metrics and malformed IDs.

### CP-003 — Build reproducible synthetic longitudinal dataset
**Labels:** `B-core`, `data`, `evaluation`, `P0-application-blocking`  
**Depends on:** CP-002  
**Acceptance criteria:**
- 10 personas generated from code;
- required durations and domains are represented;
- change points, missingness and contradictions are documented;
- fixed random seeds reproduce the dataset.

### CP-004 — Implement CSV and limited FHIR import
**Labels:** `B-core`, `data`, `backend`, `P1-required`  
**Depends on:** CP-002  
**Acceptance criteria:**
- CSV import supports frozen observations;
- FHIR mapping supports Patient, Observation, Goal and CarePlan;
- unsupported resources return explicit errors;
- import tests pass.

### CP-005 — Implement longitudinal analysis tools
**Labels:** `B-core`, `agent`, `data`, `P0-application-blocking`  
**Depends on:** CP-003  
**Acceptance criteria:**
- period comparison, trend, missingness and adherence tools implemented;
- deterministic unit tests cover normal, missing and conflicting data;
- outputs include source observation IDs.

### CP-006 — Curate trusted evidence corpus and metadata
**Labels:** `B-core`, `rag`, `data`, `P1-required`  
**Acceptance criteria:**
- at least 15 documents registered;
- metadata required by scope is complete;
- licensing or redistribution notes are recorded;
- ingestion is reproducible.

### CP-007 — Implement dual retrieval
**Labels:** `B-core`, `rag`, `agent`, `P0-application-blocking`  
**Depends on:** CP-003, CP-006  
**Acceptance criteria:**
- personal and external retrieval use separate stores or namespaces;
- results retain stable evidence identifiers;
- retrieval tests and initial Recall@5 evaluation exist.

### CP-008 — Implement deterministic safety triage
**Labels:** `B-core`, `safety`, `agent`, `P0-application-blocking`  
**Acceptance criteria:**
- rules are outside the LLM;
- routine, caution and urgent outputs are supported;
- safety test fixtures exist;
- prohibited diagnosis and medication behaviours are documented.

### CP-009 — Implement CarePath agent state graph
**Labels:** `B-core`, `agent`, `P0-application-blocking`  
**Depends on:** CP-005, CP-007, CP-008  
**Acceptance criteria:**
- all frozen nodes are implemented;
- workflow state is serialisable;
- retries are bounded;
- tool failures produce controlled responses.

### CP-010 — Implement intervention planner and adaptation
**Labels:** `B-core`, `agent`, `backend`, `P0-application-blocking`  
**Depends on:** CP-009  
**Acceptance criteria:**
- structured seven-day plans are produced;
- accepted, rejected and incomplete actions are persisted;
- a repeated failure causes a smaller or different next action;
- adaptation is demonstrated by an automated scenario.

### CP-011 — Implement grounding and safety verifier
**Labels:** `B-core`, `safety`, `rag`, `agent`, `P0-application-blocking`  
**Depends on:** CP-009, CP-010  
**Acceptance criteria:**
- unsupported claims, missing citations, prohibited advice and contradictions are checked;
- one bounded regeneration is supported;
- verifier decisions appear in the audit trail.

### CP-012 — Implement FastAPI contract
**Labels:** `B-core`, `backend`, `P0-application-blocking`  
**Depends on:** CP-002, CP-009  
**Acceptance criteria:**
- all frozen endpoints exist;
- OpenAPI and Pydantic validation work;
- structured errors and interaction IDs are returned;
- API integration tests pass.

### CP-013 — Implement audit trail
**Labels:** `B-core`, `backend`, `safety`, `P1-required`  
**Depends on:** CP-009, CP-012  
**Acceptance criteria:**
- tool, retrieval, safety, planning and verification events are stored in order;
- `/audit/{interaction_id}` returns a reviewer-readable trace;
- sensitive raw text is minimised in logs.

### CP-014 — Build React Native application shell
**Labels:** `B-core`, `mobile`, `P0-application-blocking`  
**Depends on:** CP-012  
**Acceptance criteria:**
- Expo/TypeScript project runs;
- navigation includes Today, Coach, Health Data and Plan & History;
- API client handles loading and controlled errors.

### CP-015 — Complete primary mobile user journey
**Labels:** `B-core`, `mobile`, `P0-application-blocking`  
**Depends on:** CP-010, CP-014  
**Acceptance criteria:**
- import, question, trend display, evidence display, plan and feedback work end to end;
- no API console is required to complete the main scenario;
- screenshot or video evidence is attached.

### CP-016 — Build fixed 48-scenario evaluation set
**Labels:** `B-core`, `evaluation`, `safety`, `P0-application-blocking`  
**Depends on:** CP-003, CP-006, CP-008  
**Acceptance criteria:**
- all required categories and counts exist;
- expected tools, evidence, safety outcome and prohibited claims are annotated;
- scenarios are version controlled.

### CP-017 — Implement B0–B3 baselines and metrics
**Labels:** `B-core`, `evaluation`, `P0-application-blocking`  
**Depends on:** CP-007, CP-009, CP-016  
**Acceptance criteria:**
- all four systems run through one evaluation interface;
- required retrieval, grounding, tool, safety and latency metrics are produced;
- raw and summarised outputs are saved reproducibly.

### CP-018 — Pass B acceptance thresholds
**Labels:** `B-core`, `evaluation`, `safety`, `P0-application-blocking`  
**Depends on:** CP-011, CP-017  
**Acceptance criteria:**
- all frozen internal thresholds pass;
- failures are categorised and analysed;
- no metric is represented as clinical validation.

### CP-019 — Containerise and deploy backend
**Labels:** `B-core`, `deployment`, `P1-required`  
**Depends on:** CP-012  
**Acceptance criteria:**
- Docker Compose starts required local services;
- cloud backend deployment is accessible;
- environment variables and health checks are documented.

### CP-020 — Deploy reviewer-facing client
**Labels:** `B-core`, `deployment`, `mobile`, `P1-required`  
**Depends on:** CP-015, CP-019  
**Acceptance criteria:**
- Expo Web or equivalent reviewer-facing deployment works;
- primary scenario can be completed against the deployed backend;
- a fallback local-demo procedure is documented.

### CP-021 — Produce B README and architecture diagram
**Labels:** `B-core`, `documentation`, `P1-required`  
**Depends on:** CP-015, CP-018, CP-019  
**Acceptance criteria:**
- first screen explains problem, architecture, result and startup;
- limitations and non-goals are visible;
- clean-environment setup has been tested.

### CP-022 — Produce B technical report and demo
**Labels:** `B-core`, `documentation`, `P0-application-blocking`  
**Depends on:** CP-018, CP-020, CP-021  
**Acceptance criteria:**
- 4–6 page report complete;
- 90–120 second video shows a real end-to-end run;
- CV paragraph and motivation-letter paragraph are finalised.

## Post-B / secondary branches

### CP-101 — Add Radeon local provider and benchmarks
**Labels:** `amd-extension`, `deployment`, `P3-post-B`

### CP-102 — Produce AMD submission package
**Labels:** `amd-extension`, `documentation`, `P3-post-B`

### CP-201 — Add bounded Tokyo open-data adapter
**Labels:** `tokyo-extension`, `data`, `P3-post-B`

### CP-202 — Add multilingual Tokyo resource scenario
**Labels:** `tokyo-extension`, `mobile`, `documentation`, `P3-post-B`

## Inbox — requires Scope Change Gate

Any new feature begins here with label `scope-review`. It may not enter Ready until the six Scope Change Gate questions in `PROJECT_SCOPE.md` are answered.
