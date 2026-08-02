# CarePath Issue Board

This board tracks only the current public backlog. Completed work remains documented in the implementation, tests, project documentation, closed issues, and merged pull requests rather than as open board entries.

## Board policy

- Work-in-progress limit: **2**.
- An issue enters **Ready** only when its dependencies are complete and its acceptance criteria are testable.
- `B-core` work takes precedence over secondary extensions.
- AMD and Tokyo work do not begin while a P0 B issue is blocked or incomplete.
- GitHub issue numbers are repository-local; `CP-*` identifiers are the stable planning references.

## In progress

### [#2 — CP-017: Implement B0–B3 baselines and metrics](../../issues/2)

**Labels:** `B-core`, `evaluation`, `P0-application-blocking`  
**Dependencies:** CP-007, CP-009, and CP-016 are complete.  
**Acceptance criteria:**

- all four systems run through one evaluation interface;
- required retrieval, grounding, tool, safety, and latency metrics are produced;
- raw and summarised outputs are saved reproducibly.

## Ready

### [#4 — CP-019: Containerise and deploy backend](../../issues/4)

**Labels:** `B-core`, `deployment`, `P1-required`  
**Dependencies:** CP-012 is complete.  
**Acceptance criteria:**

- Docker Compose starts required local services;
- cloud backend deployment is accessible;
- environment variables and health checks are documented.

## Blocked

### [#3 — CP-018: Pass B acceptance thresholds](../../issues/3)

**Blocked by:** CP-017.  
**Acceptance criteria:**

- all frozen internal thresholds pass;
- failures are categorised and analysed;
- no metric is represented as clinical validation.

### [#5 — CP-020: Deploy reviewer-facing client](../../issues/5)

**Blocked by:** CP-019.  
**Acceptance criteria:**

- Expo Web or equivalent reviewer-facing deployment works;
- the primary scenario can be completed against the deployed backend;
- a fallback local-demo procedure is documented.

### [#6 — CP-021: Produce B README and architecture diagram](../../issues/6)

**Blocked by:** CP-018 and CP-019.  
**Acceptance criteria:**

- the first screen explains the problem, architecture, result, and startup;
- limitations and non-goals are visible;
- clean-environment setup has been tested.

### [#7 — CP-022: Produce B technical report and demo](../../issues/7)

**Blocked by:** CP-018, CP-020, and CP-021.  
**Acceptance criteria:**

- a 4–6 page report is complete;
- a 90–120 second video shows a real end-to-end run;
- the reusable project-summary text is finalised.

## Post-B backlog

### [#8 — CP-101: Add Radeon local provider and benchmarks](../../issues/8)

**Labels:** `amd-extension`, `deployment`, `P3-post-B`

### [#9 — CP-102: Produce AMD submission package](../../issues/9)

**Labels:** `amd-extension`, `documentation`, `P3-post-B`

### [#10 — CP-201: Add bounded Tokyo open-data adapter](../../issues/10)

**Labels:** `tokyo-extension`, `data`, `P3-post-B`

### [#11 — CP-202: Add multilingual Tokyo resource scenario](../../issues/11)

**Labels:** `tokyo-extension`, `mobile`, `documentation`, `P3-post-B`

## Inbox — Scope Change Gate

Any new feature begins with `scope-review`. It may not enter Ready until the Scope Change Gate questions in `PROJECT_SCOPE.md` are answered.
