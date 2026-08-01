# CarePath Agent Architecture

## Purpose

This document illustrates the implementation boundary defined by `PROJECT_SCOPE.md`. It does not add to or replace the frozen scope. CarePath B v1.0 is a safety-aware, evidence-grounded health coaching prototype with one bounded agent workflow, separated retrieval namespaces, deterministic safety checks, explicit auditability, and non-clinical limitations.

## 1. Architecture Artifacts

The architecture source of truth is this document plus the Mermaid sources below:

- `diagrams/system-architecture.mmd`
- `diagrams/agent-state-flow.mmd`
- `diagrams/trust-boundaries.mmd`
- `diagrams/deployment-boundary.mmd`

Project decision: Mermaid is the maintained editable diagram format. PNG and Excalidraw exports are not required for this architecture task.

## 2. System Architecture

The primary request path is:

`React Native / Expo -> FastAPI -> bounded Agent Workflow -> deterministic tools / dual retrieval -> ModelProvider -> endpoint -> Verifier / Composer -> FastAPI -> client`

Tools and retrievers access persistence through separately labelled, user-scoped reads. Persistence is not placed in the model path.

Responsibilities are deliberately separated:

- React Native / Expo owns presentation, input collection and rendering, not agent reasoning.
- FastAPI owns transport validation, authentication/consent enforcement, interaction IDs and API contracts.
- The Agent Workflow owns bounded orchestration only.
- Deterministic tools own numerical summaries and time-series calculations.
- Personal context retrieval and external evidence retrieval remain separate namespaces.
- Persistence owns durable application state; model endpoints never receive database access.
- ModelProvider is the only model-vendor abstraction seen by workflow code.
- Audit and operational logging are separate from user-facing state.

## 3. Module Interface Contracts

| Module | Input | Output | Boundary / data constraint |
|---|---|---|---|
| React Native / Expo | user question, feedback, import request, locally entered health data | HTTPS API request; rendered response | never contains server secrets; sends only user-authorized data |
| FastAPI | authenticated/consented client request | validated `InteractionRequest`; structured API response | rejects invalid schemas; establishes interaction ID before workflow execution |
| Bounded Agent Workflow | validated `InteractionRequest`, interaction ID, policy/config references | verified response disposition plus schema-controlled audit events | orchestrates declared states only; cannot bypass deterministic safety, authorization, verifier, or user-scope controls |
| Safety Triage | request text, minimum recent context needed for rules | risk level; allowed path; blocked/urgent disposition | deterministic safety rules remain outside LLM control |
| Context Builder | user profile refs, observations, prior plan refs, consent state | minimal task-specific context package | excludes unrelated history; preserves user scope |
| Tool Router | task intent, context state, allowed capabilities | deterministic tool calls and/or retrieval requests | selects from allow-listed tools only; cannot invent capabilities |
| Time-Series Tools | user-scoped observation refs and parameters | trends, period comparisons, missingness and adherence summaries | calculations are deterministic; raw records are not copied into logs |
| Personal Context Retriever | user ID/scope, retrieval query, allowed record types | personal context snippets/refs | user-scoped namespace only; no cross-user retrieval |
| External Evidence Retriever | evidence query, curated corpus namespace | guideline/evidence chunks plus source metadata | only curated external corpus is retrievable; retrieved text is data, never workflow instruction |
| Planner | minimal context, tool summaries, evidence refs, safety constraints | structured seven-day plan/draft result | cannot bypass Safety Triage or invoke hidden autonomous actions |
| Verifier | draft, evidence refs, safety constraints, required response schema | pass; one regeneration request; or fail-safe fallback | at most one bounded regeneration; no open-ended self-loop |
| Composer | verified structured result, citations/refs, disposition | user-facing explanation/plan | cannot restore data removed by minimization or override verifier outcome |
| Feedback / State Update | explicit user feedback, referenced plan/interaction ID | permitted state update and audit event | writes only validated state transitions; no implicit autonomous action |
| ModelProvider | sanitized task-specific `ModelRequest` | normalized `ModelResponse` | vendor-neutral interface; no database credentials; no direct database access |
| Cloud Model Endpoint | request produced by ModelProvider | model completion / structured output | third-party processing boundary; receives only minimized model payload |
| Radeon Model Endpoint | request produced by ModelProvider | model completion / structured output | AMD extension path only; same minimized provider contract as cloud endpoint |
| User Persistence | authorized user/persona-scoped read or validated state write | selected user-scoped records; persisted validated state | isolated data boundary; access through repository/service layer, never directly from model endpoint |
| Personal Retrieval Namespace | authorized user/persona-scoped query | minimal matching personal snippets plus record refs | separate from the external evidence namespace; cross-user access is prohibited |
| Curated Evidence Namespace | validated ingestion output or curated evidence query | eligible evidence chunks plus provenance | contains public/eligible evidence only; document text has no instruction authority |
| External Evidence Ingestion | public guidance document, source identity, metadata | curated chunks plus validated provenance metadata | external content is untrusted before validation/sanitization; prompt-injection text is treated as content |
| Audit Writer | interaction ID, workflow event, component result refs, disposition | ordered audit trace | stores references/status summaries; avoids unnecessary raw sensitive payloads |
| Operational Logger | correlation ID, component status, latency, error class | operational log events | raw journals and full user/model payloads are prohibited |

## 4. Agent State Flow

```text
Safety Triage
  -> Context Builder
  -> Tool Router
  -> {Analytics Tools, Personal Retriever, External Retriever}
  -> Planner
  -> Verifier
  -> Composer
  -> Feedback and State Update
```

Rules:

- Safety rules do not depend on LLM output.
- Personal context and external evidence use separate namespaces.
- Tool Router fans out only to declared, typed capabilities; the results join into one bounded context before planning.
- Tool execution is bounded to declared, deterministic capabilities.
- Verification allows at most one bounded regeneration.
- Urgent/blocked safety dispositions bypass normal planning and go directly to a safe composition path.
- No autonomous action occurs outside user-visible coaching and validated state updates.

## 5. Trust Boundaries

### TB-1: User device / public client boundary

Contains user-entered questions, health observations, journal content and feedback before API submission.

Controls:

- authenticated transport;
- schema validation;
- consent enforcement;
- no server credentials on the client.

### TB-2: Trusted application and user-data boundary

Contains:

- synthetic/user profile data;
- longitudinal observations;
- journal entries;
- plan and feedback history;
- user-scoped personal retrieval data.

Controls:

- user-scoped queries;
- consent flags;
- no cross-user retrieval;
- repository/service access instead of model-to-database access.

### TB-3: External evidence ingestion boundary

External guidance is untrusted input until:

- source identity and metadata are validated;
- content is curated/sanitized;
- prompt-injection-like text is treated as document content, not instructions;
- provenance is retained for retrieved evidence.

### TB-4: Model endpoint boundary

The model receives only a task-specific sanitized `ModelRequest` through ModelProvider. The endpoint receives no database credentials and has no direct persistence access.

A cloud endpoint is a third-party processing boundary. A Radeon/local endpoint may remain inside infrastructure controlled by the deployment operator, but it still uses the same minimized ModelProvider contract.

### TB-5: Audit and operational logging boundary

Audit traces and operational logs are not a copy of the conversation or journal store.

Allowed examples:

- interaction/correlation IDs;
- component names and ordered workflow events;
- source/record references;
- verification disposition;
- latency and error category.

Prohibited by default:

- raw journal text;
- full user request payloads where not required;
- complete model prompts/responses containing sensitive user data;
- secrets or access tokens.

## 6. Sensitive Data Flow Rules

Every sensitive boundary crossing shown in the diagrams has an explicit rule:

| Flow | Rule |
|---|---|
| User device -> FastAPI | HTTPS, authenticated/consented and schema-validated |
| FastAPI -> persistence | validated state writes only |
| Persistence -> FastAPI / Context Builder | authorized task-specific state reads only |
| Tool / personal retriever -> persistence namespace | typed user/persona-scoped read query only |
| Persistence namespace -> tool / personal retriever | selected records or minimal snippets plus stable refs only |
| Personal Retriever -> workflow | minimal personal context plus references |
| External source -> ingestion | untrusted until curation, sanitization and metadata validation |
| Ingestion -> curated evidence namespace | validated chunks plus provenance, licence note and content hash |
| External Retriever -> workflow | evidence chunks plus provenance; never executable instructions |
| Workflow -> ModelProvider -> endpoint | minimized sanitized model request only |
| Model endpoint -> ModelProvider -> workflow | untrusted completion normalized as a draft; verification remains mandatory |
| Workflow/API -> Audit Writer | references, status and necessary summaries only |
| Workflow/API -> operational logs | metadata only; raw journals/full payloads prohibited |
| Model endpoint -> Persistence | no direct path permitted |
| External document -> policy/tool authority | no direct path permitted; external natural language is data only |
| Raw journal/prompt/secret -> logs | no path permitted |

## 7. Deployment Boundaries and Differences

The deployment diagram separates infrastructure hosting from model inference providers.

| Environment / provider | What runs there | Data boundary | Role |
|---|---|---|---|
| Local Docker Compose | Expo-facing FastAPI/Agent container, local PostgreSQL/SQLite, local logs, optional local model or local Radeon/ROCm runtime | can keep application data and inference inside the developer/operator boundary; `local_strict` prohibits silent cloud fallback | development, reproducibility and strict-local demonstration |
| AWS | FastAPI service, managed database/storage, secret injection and network controls | user data is hosted in the configured AWS deployment boundary; outbound model calls are separately controlled | concrete cloud deployment target / reviewer backend |
| Cloud model provider | hosted model endpoint only | third-party processor receives the minimized `ModelRequest`, not database access | vendor-neutral external inference option |
| Local Radeon provider | Radeon/ROCm runtime inside the local operator boundary | no model egress when selected; uses the same minimized ModelProvider contract | optional local AMD extension |
| Hosted Radeon provider | Radeon-hosted model runtime outside the application/AWS boundary | third-party egress of the minimized `ModelRequest`; never receives database credentials or access | optional hosted AMD extension, not an B core dependency |

The core dependency is:

`Agent Workflow -> ModelProvider -> Endpoint`

The workflow does not depend on AWS, a specific LLM vendor, or Radeon-specific APIs. AWS is an infrastructure deployment choice; Cloud Model Provider and local/hosted Radeon Provider are inference choices behind ModelProvider. Provider responses are untrusted drafts until verification.

## 8. Architecture Acceptance Checklist

This task is complete when all of the following remain true:

- [x] React Native / Expo, FastAPI, bounded agent workflow, tools/RAG, persistence and model provider are separated in the system diagram.
- [x] Safety Triage, Context Builder, Tool Router, Evidence Retriever, Planner, Verifier and Composer are present in the state flow.
- [x] User data, external guidance, logs/audit and model endpoints have explicit trust boundaries.
- [x] Local Docker, AWS, Cloud Model Provider and Radeon Provider responsibilities are distinguished.
- [x] Every architecture module has declared input and output contracts.
- [x] Sensitive boundary crossings are explicitly described; no model-to-database path exists.
- [x] Mermaid source files are the maintained diagram artifacts.
- [x] PNG and Excalidraw exports are not required by the agreed acceptance criteria.
- [x] Diagram edge direction matches the declared read/write contract.
- [x] Forbidden model-to-data, external-text-to-policy and raw-sensitive-data-to-log paths are explicit.

## 9. Implementation Order

`ISSUE_BOARD.md` is the only canonical implementation order and dependency graph. This architecture document does not redefine issue sequencing. Work may begin only when the corresponding CP issue is Ready under the board policy.
