# CarePath Agent — B Main Project Scope

**Status:** FROZEN for the B application version  
**Scope owner:** CarePath Contributor  
**Canonical document:** `PROJECT_SCOPE.md`  
**Last updated:** 2026-07-24  
**Primary objective:** Demonstrate readiness for the B/Singapore-B Centre PhD project on trustworthy agentic AI for personalised health coaching.  
**Secondary objectives:** Reuse the core system for AMD and Tokyo Open Data hackathon submissions without weakening or delaying the B version.

> **Scope rule:** A feature is not part of the B main project unless it is explicitly listed in this document or passes the Scope Change Gate in Section 15.

---

## 1. Project name and one-line positioning

### Name

**CarePath Agent**

### Descriptive title

**CarePath Agent: Evidence-Grounded Adaptive Health Coaching from Longitudinal Multimodal Data**

### One-line positioning

CarePath Agent is a safety-aware mobile health coaching system that analyses longitudinal wearable-style data, user-reported context, and trusted health guidance to generate evidence-grounded, personalised, and adaptively revised behaviour-change plans.

### What makes it an agentic system

CarePath does not answer every request with a single language-model call. It maintains interaction state, selects analytical and retrieval tools, distinguishes personal observations from external evidence, produces an action plan, verifies safety and grounding, records an audit trace, and adapts later recommendations from user feedback.

---

## 2. Problem statement

Most health chatbots generate generic advice from the latest message. They commonly fail to:

- reason over trends across several weeks;
- combine heterogeneous personal data with external evidence;
- distinguish observed facts from general health knowledge;
- adapt an intervention after the user accepts, rejects, or fails to complete it;
- make uncertainty and safety boundaries visible;
- provide an auditable explanation of which data and tools influenced an answer.

CarePath addresses this gap with a research-facing application prototype. It is designed to demonstrate trustworthy agentic workflows for behavioural support, not clinical diagnosis or treatment.

---

## 3. Frozen behavioural domains

The B main version covers exactly four behavioural domains:

1. **Sleep**
   - sleep duration;
   - sleep timing and regularity;
   - self-reported sleep quality;
   - non-clinical sleep-hygiene actions.

2. **Physical activity**
   - steps;
   - active minutes;
   - sedentary periods;
   - realistic activity goals and adherence.

3. **Stress and mood**
   - self-reported stress score;
   - self-reported mood score;
   - journal context;
   - low-risk stress-management actions and motivational support.

4. **Falls and activity safety**
   - self-reported balance concern;
   - recent near-fall or fall flag;
   - activity confidence;
   - safe-activity planning and escalation guidance.

No fifth domain may be added before the B version is complete.

---

## 4. Primary scenario

### Primary persona

A working-age adult or postgraduate student who uses a phone or wearable device, has several weeks of activity and sleep records, records stress or mood periodically, and wants practical support for maintaining healthier routines.

The system also includes a synthetic older-adult persona to test falls and activity-safety behaviour. This persona is for safety evaluation, not a claim that the prototype is validated for older adults.

### Primary scenario

Over the past two weeks, the user’s average sleep duration has fallen, resting heart rate has increased relative to the previous two weeks, daily activity has declined, and journal entries mention workload and fatigue. The user asks:

> “I have felt more tired recently. What changed, and what is a realistic plan for this week?”

CarePath must:

1. screen the request and recent context for safety concerns;
2. retrieve the relevant personal history;
3. calculate the relevant seven-day and twenty-eight-day trends;
4. retrieve trusted guidance relevant to sleep, activity, and stress;
5. identify what is observed, what is inferred, and what remains uncertain;
6. generate a small, feasible seven-day action plan;
7. provide evidence references and safety boundaries;
8. let the user accept, reject, or modify the plan;
9. use that feedback in a later recommendation.

---

## 5. Main user story

> **As a user**, I want CarePath to review my recent health-behaviour data and personal context, explain important changes without pretending to diagnose me, and propose a small evidence-grounded plan that can be adjusted according to my preferences and previous adherence.

### Supporting user stories

- As a user, I can see which personal observations influenced the response.
- As a user, I can inspect the external sources supporting general health statements.
- As a user, I can accept, reject, reduce, or replace a suggested action.
- As a user, I can see how the current plan differs from a previous plan.
- As a user, I receive conservative escalation guidance when safety rules are triggered.
- As a researcher or reviewer, I can inspect an audit trace of retrievals, tool calls, safety decisions, and plan revisions.

---

## 6. Complete input and output contract

## 6.1 Inputs

### A. User profile

- age band, not exact date of birth;
- preferred language;
- broad daily schedule constraints;
- behavioural goals;
- activity limitations or safety preferences;
- preferred coaching style;
- consent flags for data categories.

### B. Longitudinal observations

The prototype must support 30–60 days of synthetic or openly licensed data containing:

- sleep duration;
- sleep start and end time;
- self-reported sleep quality;
- daily steps;
- active minutes;
- resting heart rate;
- stress score;
- mood score;
- fall or near-fall event flag;
- activity-confidence score;
- missingness and data-source metadata.

### C. Free-text context

- journal entry;
- user question;
- user explanation for adherence or non-adherence;
- user plan feedback.

### D. Knowledge sources

- trusted public health or behavioural guidance;
- document title, issuing organisation, publication/update date, section, URL and chunk identifier;
- source trust category and retrieval date.

### E. System state

- active goal;
- current plan;
- previous plans;
- action completion history;
- rejected actions;
- previous safety decisions;
- interaction audit history.

## 6.2 Outputs

Every successful coaching interaction returns:

```json
{
  "interaction_id": "uuid",
  "risk_level": "routine | caution | urgent",
  "observed_changes": [
    {
      "statement": "Average sleep duration fell by 1.1 hours compared with the previous 14 days.",
      "observation_ids": ["obs-..."],
      "confidence": "high"
    }
  ],
  "interpretation": {
    "summary": "The available data suggests a recent combination of shorter sleep, lower activity, and higher self-reported stress.",
    "uncertainties": ["Resting heart-rate data is missing on four days."],
    "diagnosis_claimed": false
  },
  "plan": {
    "duration_days": 7,
    "goal": "Restore a more regular evening routine and reintroduce manageable activity.",
    "actions": [
      {
        "action_id": "act-...",
        "description": "Take a 10-minute walk after dinner on three days.",
        "frequency": "3 times this week",
        "difficulty": "low",
        "rationale": "Selected because activity declined and the previous 10,000-step goal was not completed."
      }
    ]
  },
  "evidence": [
    {
      "source_id": "src-...",
      "chunk_id": "chunk-...",
      "supports": ["claim-..."],
      "title": "...",
      "organisation": "..."
    }
  ],
  "safety_message": "This system does not diagnose conditions. Seek professional care if ...",
  "follow_up": {
    "review_after_days": 7,
    "questions": ["Which action felt easiest to complete?"]
  },
  "audit_url": "/audit/uuid"
}
```

The mobile interface may simplify this structure visually, but the backend response and audit record must retain it.

---

## 7. Canonical data schema

The schema is intentionally small and interoperable. PostgreSQL is the target database; SQLite is permitted during local development. UUIDs are used for entity identifiers. All timestamps use ISO 8601 UTC internally.

## 7.1 Core entities

### `UserProfile`

| Field | Type | Required | Notes |
|---|---|---:|---|
| `user_id` | UUID | Yes | Synthetic user identifier |
| `age_band` | enum | Yes | `18-29`, `30-44`, `45-64`, `65+` |
| `preferred_language` | enum | Yes | `en`, `zh`, `ja` |
| `timezone` | string | Yes | IANA timezone |
| `schedule_constraints` | JSON | No | Available times and routine constraints |
| `health_goals` | string[] | Yes | Limited to the four frozen domains |
| `activity_constraints` | string[] | No | User-provided, not clinically verified |
| `coaching_preferences` | JSON | No | Tone, reminder frequency, plan size |
| `consent_flags` | JSON | Yes | Per-category prototype consent |

### `Observation`

| Field | Type | Required | Notes |
|---|---|---:|---|
| `observation_id` | UUID | Yes | |
| `user_id` | UUID | Yes | |
| `metric_type` | enum | Yes | Frozen metric vocabulary below |
| `value_numeric` | float | Conditional | For numeric metrics |
| `value_boolean` | boolean | Conditional | For event flags |
| `unit` | string | Conditional | e.g. `hours`, `steps`, `bpm`, `score_1_10` |
| `observed_at` | datetime | Yes | |
| `source_type` | enum | Yes | `synthetic_wearable`, `self_report`, `csv`, `fhir` |
| `quality_flag` | enum | Yes | `valid`, `missing`, `suspect` |
| `metadata` | JSON | No | Device or generation metadata |

Frozen `metric_type` values:

- `sleep_duration`
- `sleep_start_time`
- `sleep_end_time`
- `sleep_quality`
- `steps`
- `active_minutes`
- `resting_heart_rate`
- `stress_score`
- `mood_score`
- `fall_event`
- `near_fall_event`
- `activity_confidence`

### `JournalEntry`

| Field | Type | Required |
|---|---|---:|
| `entry_id` | UUID | Yes |
| `user_id` | UUID | Yes |
| `created_at` | datetime | Yes |
| `text` | text | Yes |
| `language` | enum | Yes |
| `user_tags` | string[] | No |

### `Goal`

| Field | Type | Required |
|---|---|---:|
| `goal_id` | UUID | Yes |
| `user_id` | UUID | Yes |
| `domain` | enum | Yes |
| `description` | text | Yes |
| `status` | enum | Yes |
| `created_at` | datetime | Yes |
| `target_date` | date | No |

### `CarePlan`

| Field | Type | Required |
|---|---|---:|
| `plan_id` | UUID | Yes |
| `user_id` | UUID | Yes |
| `goal_id` | UUID | Yes |
| `version` | integer | Yes |
| `start_date` | date | Yes |
| `end_date` | date | Yes |
| `status` | enum | Yes |
| `generation_interaction_id` | UUID | Yes |
| `supersedes_plan_id` | UUID | No |

### `PlanAction`

| Field | Type | Required |
|---|---|---:|
| `action_id` | UUID | Yes |
| `plan_id` | UUID | Yes |
| `domain` | enum | Yes |
| `description` | text | Yes |
| `frequency` | string | Yes |
| `difficulty` | enum | Yes |
| `rationale` | text | Yes |
| `status` | enum | Yes |

### `ActionFeedback`

| Field | Type | Required |
|---|---|---:|
| `feedback_id` | UUID | Yes |
| `action_id` | UUID | Yes |
| `user_id` | UUID | Yes |
| `response` | enum | Yes |
| `completion_ratio` | float | No |
| `reason_text` | text | No |
| `created_at` | datetime | Yes |

`response` values: `accepted`, `rejected`, `modified`, `completed`, `partially_completed`, `not_completed`.

### `KnowledgeSource`

| Field | Type | Required |
|---|---|---:|
| `source_id` | string | Yes |
| `title` | text | Yes |
| `organisation` | text | Yes |
| `url` | text | Yes |
| `published_or_updated_at` | date | No |
| `retrieved_at` | date | Yes |
| `trust_tier` | enum | Yes |
| `licence_note` | text | Yes |

### `KnowledgeChunk`

| Field | Type | Required |
|---|---|---:|
| `chunk_id` | string | Yes |
| `source_id` | string | Yes |
| `section_title` | text | No |
| `content` | text | Yes |
| `embedding_model` | string | Yes |
| `content_hash` | string | Yes |

### `Interaction`

| Field | Type | Required |
|---|---|---:|
| `interaction_id` | UUID | Yes |
| `user_id` | UUID | Yes |
| `request_text` | text | Yes |
| `language` | enum | Yes |
| `started_at` | datetime | Yes |
| `completed_at` | datetime | No |
| `risk_level` | enum | Yes |
| `final_status` | enum | Yes |
| `response_json` | JSON | No |

### `AuditEvent`

| Field | Type | Required |
|---|---|---:|
| `audit_event_id` | UUID | Yes |
| `interaction_id` | UUID | Yes |
| `sequence_number` | integer | Yes |
| `event_type` | enum | Yes |
| `component` | string | Yes |
| `input_refs` | JSON | Yes |
| `output_summary` | JSON | Yes |
| `created_at` | datetime | Yes |

Audit event types include `safety_decision`, `retrieval`, `tool_call`, `tool_result`, `plan_generated`, `verification`, `plan_revised`, and `response_emitted`.

## 7.2 FHIR compatibility boundary

The prototype supports a deliberately limited import mapping:

- `Patient` → `UserProfile`
- `Observation` → `Observation`
- `Goal` → `Goal`
- `CarePlan` → `CarePlan` and `PlanAction`

It does not claim full FHIR conformance. Unsupported resources must be rejected with a clear validation response rather than silently ignored.

---

## 8. Frozen agent workflow

The B version contains one orchestrated agent workflow with the following nodes:

1. **Safety Triage**
2. **Context Builder**
3. **Tool Router**
4. **Time-Series Analysis Tools**
5. **Personal Context Retriever**
6. **External Evidence Retriever**
7. **Intervention Planner**
8. **Grounding and Safety Verifier**
9. **Response Composer**
10. **Feedback and State Update**

Required analytical tools:

- `compare_periods`
- `compute_trend`
- `summarise_missingness`
- `summarise_adherence`
- `retrieve_personal_context`
- `retrieve_external_evidence`

The verifier may request one regeneration. Infinite or open-ended agent loops are prohibited.

---

## 9. B application-grade minimum standard

The project is not complete unless every item below passes.

## 9.1 Longitudinal data

- At least 10 synthetic personas.
- At least 30 days of data per persona; at least 3 personas have 60 days.
- All four behavioural domains represented across the dataset.
- Missing values, conflicting self-reports, and injected changes are represented.
- Data generation is reproducible from code and documented seeds.
- CSV import works.
- Limited FHIR Bundle import works for the four mapped resource types.

## 9.2 RAG

- Personal context retrieval and external evidence retrieval are logically separated.
- At least 15 trusted external source documents are indexed.
- Every external chunk retains source, organisation, URL, date, section and chunk ID.
- Responses contain claim-level or section-level source references.
- Retrieval evaluation includes Recall@5 or equivalent evidence coverage.
- The system does not treat personal journal content as authoritative medical knowledge.

## 9.3 Agent behaviour

- The workflow selects tools according to the request and data state.
- At least four tool types are invoked in the test suite.
- Interaction state persists across plan creation and feedback.
- A rejected or repeatedly uncompleted action changes the next plan.
- Every interaction produces an audit trace.
- A failed tool call returns a controlled error or fallback response.

## 9.4 React Native application

The React Native/Expo client must include:

1. **Today** — current summary, priority action, recent trend.
2. **Coach** — conversation, tool-status indication, evidence expansion.
3. **Health Data** — trend visualisation and synthetic-data import.
4. **Plan & History** — current plan, previous version, action feedback.

A reviewer must be able to complete the primary scenario from the interface without using API documentation.

## 9.5 FastAPI backend

Required endpoints:

- `POST /profiles`
- `POST /records/import`
- `POST /fhir/bundle`
- `GET /records/trends`
- `POST /coach/message`
- `GET /plans/current`
- `POST /plans/{plan_id}/feedback`
- `GET /audit/{interaction_id}`
- `GET /health`

Requirements:

- Pydantic validation;
- OpenAPI documentation;
- structured error responses;
- request correlation or interaction IDs;
- automated API tests.

## 9.6 Safety

- Deterministic red-flag rules exist outside the LLM.
- Safety-sensitive cases are tested separately from routine coaching.
- The system does not produce a definitive diagnosis.
- The system does not instruct the user to start, stop, or change medication.
- Missing or conflicting data lowers stated certainty.
- Prompt injection in retrieved documents is treated as untrusted content.
- Safety and grounding verification occurs before response emission.
- The UI shows that the system is a research prototype and not a medical service.

## 9.7 Evaluation

Minimum evaluation set: **48 fixed scenarios**.

Required categories:

- 16 routine coaching scenarios;
- 8 longitudinal trend scenarios;
- 8 missing or conflicting data scenarios;
- 8 safety escalation scenarios;
- 4 prompt-injection or hostile-document scenarios;
- 4 multilingual scenarios across English, Chinese, and Japanese.

Required baselines:

- B0: LLM only;
- B1: external-guideline RAG;
- B2: personal-context plus external-guideline RAG;
- B3: complete CarePath agent.

Required reported measures:

- evidence retrieval coverage;
- citation precision;
- patient-context fidelity;
- unsupported-claim rate;
- tool-selection accuracy;
- tool-execution success;
- safety escalation recall;
- contradiction rate;
- end-to-end latency.

Target internal acceptance thresholds:

- safety escalation recall: 100% on the fixed safety set;
- tool-selection accuracy: at least 90%;
- patient-context fidelity: at least 90%;
- citation precision: at least 85%;
- unsupported medical claim rate: at most 10%;
- all 48 scenarios reproducibly executable.

These are engineering acceptance thresholds on synthetic test cases, not claims of clinical validity.

## 9.8 Deployment

- Local startup through Docker Compose.
- One documented cloud deployment of the FastAPI backend.
- One accessible Expo Web or equivalent reviewer-facing client deployment.
- Secrets are loaded from environment variables and are absent from the repository.
- Health check and basic logging are enabled.
- A clean-environment installation is tested from the README.

AMD-specific Radeon deployment is a secondary extension and is not required for the B core to function.

## 9.9 Presentation

The B version must include:

- public or reviewer-accessible GitHub repository;
- concise README with architecture diagram and one-command startup;
- 90–120 second demonstration video;
- 4–6 page technical report;
- evaluation table and at least one failure-analysis section;
- CV-ready project description;
- explicit limitations, ethical boundary, and non-clinical-use statement.

---

## 10. Definition of Done

CarePath B v1.0 is complete only when all of the following are true:

### Functional

- The primary scenario runs end to end from the mobile interface.
- A user can import data, ask a question, inspect trends and evidence, receive a plan, and submit feedback.
- The next recommendation visibly adapts to previous feedback.
- All required FastAPI endpoints are available and documented.

### Technical

- The frozen schema is implemented or versioned through documented migrations.
- The agent workflow and required tools are implemented.
- Docker Compose starts the local system.
- A cloud backend and reviewer-facing frontend are deployed.
- Automated tests cover core APIs, analytical tools, safety rules, and the main workflow.

### Research and evaluation

- B0–B3 are compared on the fixed scenario set.
- The required metrics are reported.
- Safety acceptance thresholds pass.
- Failures and limitations are analysed rather than hidden.
- Evaluation scripts and test scenarios are version controlled.

### Communication

- A new reviewer can understand the problem, system boundary, architecture, evaluation and limitations from the README and report.
- The demonstration video shows a real end-to-end interaction.
- Claims are limited to what the synthetic evaluation supports.

### Five-minute comprehension test

After reading this file for no more than five minutes, a reviewer must be able to answer:

1. What user problem does CarePath address?
2. What four behavioural domains are included?
3. What data enters the system?
4. What does the agent do beyond ordinary RAG?
5. What does the system return?
6. What safety boundary does it enforce?
7. What is explicitly not being built?
8. Which evidence proves that v1.0 is complete?

If two or more answers are unclear, the project scope is not sufficiently documented.

---

## 11. Explicit non-goals

The B v1.0 project will **not** include or claim:

- diagnosis of any disease or mental-health condition;
- clinical risk prediction;
- treatment recommendation;
- medication initiation, cessation, dose change, or interaction advice;
- medical-device functionality;
- emergency-service replacement;
- real patient recruitment or real patient data;
- clinical trials, clinical validation, efficacy, acceptability, or feasibility claims;
- direct integration with hospital EHR systems;
- complete FHIR conformance;
- live Apple Health, Google Fit, or commercial wearable integration;
- medical imaging, ECG, EEG, laboratory-result interpretation, or genomic analysis;
- model pretraining or fine-tuning;
- reinforcement learning;
- online learning from real users;
- a multi-agent committee, debate system, or autonomous agent society;
- unconstrained autonomous action;
- long-term autonomous memory beyond the defined user, plan, feedback and audit state;
- voice interface;
- social network or community features;
- clinician dashboard;
- payment, insurance, appointment booking, or telemedicine;
- production-grade regulatory compliance certification;
- penetration-tested production security;
- App Store or Google Play publication;
- full production observability or 24/7 service-level guarantees;
- nationwide or all-Tokyo public-resource navigation in the B core;
- hardware-device development;
- a claim that synthetic evaluation predicts real-world clinical performance.

These items may appear only under “future work” unless this scope document is formally revised after B v1.0 is complete.

---

## 12. Secondary hackathon boundary

### AMD extension

Allowed only after the relevant core interface exists:

- replaceable local LLM provider;
- Radeon/ROCm or Radeon Cloud deployment;
- latency, throughput and memory benchmarking;
- local-first privacy demonstration;
- AMD-specific submission assets.

The AMD extension must not require a redesign of the core data model, safety layer, or mobile workflow.

### Tokyo Open Data extension

Allowed only as a separate adapter or branch:

- Tokyo public-health and public-service datasets;
- location-aware resource retrieval;
- multilingual public-resource navigation;
- a small, clearly bounded geographic demonstration.

Tokyo resource navigation must not be mixed into the B evaluation baselines or presented as a core clinical capability.

---

## 13. Initial Issue Board structure

The executable issue backlog is maintained in `ISSUE_BOARD.md`.

Board columns:

1. **Inbox** — captured but not scope-approved.
2. **Ready** — in scope, acceptance criteria written, dependencies resolved.
3. **In Progress** — maximum two issues at once.
4. **Review** — code, test, documentation or evaluation review required.
5. **Blocked** — blocker and next unblock action recorded.
6. **Done** — acceptance criteria and evidence satisfied.
7. **Post-B** — valid extension, explicitly excluded from B v1.0.

Required labels:

- `B-core`
- `data`
- `backend`
- `agent`
- `rag`
- `safety`
- `mobile`
- `evaluation`
- `deployment`
- `documentation`
- `amd-extension`
- `tokyo-extension`
- `blocked`
- `scope-review`

Priority labels:

- `P0-application-blocking`
- `P1-required`
- `P2-polish`
- `P3-post-B`

---

## 14. Evidence required to close an issue

An issue is not complete because code exists. The closing comment or pull request must link to at least one of:

- passing automated test;
- reproducible command and output;
- screenshot or video of the user-facing behaviour;
- evaluation result;
- deployed endpoint;
- documentation section;
- migration or schema definition;
- failure-handling demonstration.

Issues affecting safety, schema, evaluation, or user-visible behaviour require review before moving to Done.

---

## 15. Scope Change Gate

Before adding any feature not explicitly listed in this file, answer all six questions:

1. Which B requirement or frozen success criterion does it directly support?
2. What existing acceptance criterion is currently impossible without it?
3. Can the same objective be met with a smaller implementation?
4. What is its estimated implementation, testing, documentation and debugging cost?
5. Which currently scheduled issue will be delayed or removed?
6. Does it introduce a new data category, clinical claim, safety risk, platform, model-training method, or external dependency?

### Decision rule

A proposed feature may enter the B scope only when:

- Question 1 names a direct requirement;
- Question 2 identifies a genuine gap;
- the smallest viable implementation is selected;
- its cost and displaced work are recorded;
- it does not contradict a non-goal;
- the change is written into this file before implementation begins.

Otherwise, label it `P3-post-B` and place it in the Post-B column.

### Automatic rejection conditions before B v1.0

Reject or defer a feature when it:

- adds a fifth behavioural domain;
- requires real patient data;
- requires model training or reinforcement learning;
- creates another agent or orchestration framework;
- creates another frontend;
- expands FHIR support beyond the four mapped resource types;
- adds live wearable integrations;
- exists mainly for visual novelty;
- serves only a hackathon and cannot be isolated as an adapter;
- cannot be evaluated within the frozen test framework.

---

## 16. Final scope summary

CarePath B v1.0 is a research-facing, mobile, evidence-grounded health coaching prototype. It analyses longitudinal synthetic health-behaviour data in sleep, physical activity, stress/mood, and falls/activity safety. A bounded agent workflow performs safety triage, time-series analysis, dual retrieval, intervention planning, verification and feedback-based adaptation. The system is delivered through React Native and FastAPI, evaluated against three simpler baselines, deployed for review, and documented with explicit non-clinical limitations.

Anything beyond that statement is outside the frozen B main-project scope unless it passes the Scope Change Gate.
