# CP-009 CarePath Agent State Graph

## Purpose

CarePath exposes the frozen ten-node workflow through two compatible orchestration layers:

- `CarePathWorkflow`, the original bounded synchronous orchestrator retained for existing API/tests;
- `build_carepath_langgraph`, the explicit LangGraph protocol used when a real `StateGraph` execution surface is required.

Neither layer creates open-ended autonomy. Safety, context building, tools, personal retrieval, external retrieval, planning, verification, composition and feedback remain separate typed boundaries.

## Frozen nodes

The shared `WorkflowNode` set is:

1. `safety_triage`
2. `context_builder`
3. `tool_router`
4. `analytics_tools`
5. `personal_context_retriever`
6. `external_evidence_retriever`
7. `planner`
8. `verifier`
9. `composer`
10. `feedback_update`

Normal LangGraph path:

```text
START
  -> Safety Triage
  -> Context Builder
  -> Tool Router
  -> Analytics Tools
  -> Personal Context Retriever
  -> External Evidence Retriever
  -> Planner
  -> Verifier
       -> Planner once, only when regeneration is requested
       -> Composer otherwise
  -> Composer
  -> Feedback Update
  -> END
```

A blocked safety result goes directly from Safety Triage to Composer and never enters Context Builder, tools, retrieval, Planner or Verifier. A controlled node error also routes to Composer rather than escaping as an unbounded exception path.

## Typed LangGraph state

`AgentGraphState` is a Pydantic state schema accepted by LangGraph `StateGraph`. It explicitly carries:

- `interaction_id`, `user_id` and input request text;
- typed `risk_assessment`;
- `patient_context` as Patient Evidence items;
- `selected_tools`;
- structured `tool_results`;
- separate `external_evidence` hits;
- `plan_draft`;
- `verification_result`;
- `final_response`;
- typed `error_state`;
- `model_provider`;
- bounded `retry_count`;
- ordered `node_audit_events`.

The complete state supports Pydantic JSON dump/validation round trips. Node handlers cannot change the interaction or user identity.

## Typed node protocol

Every LangGraph node receives:

```text
AgentNodeInput
  node_name
  state: AgentGraphState
```

and returns:

```text
AgentNodeOutput
  state: AgentGraphState
  result_status
  record_ids
  document_ids
  tool_parameters
```

`build_carepath_langgraph()` refuses to compile when any frozen node handler is missing. This prevents implicit chains where a required safety/retrieval/verification stage disappears from the executable graph.

## Safety gate

The default LangGraph safety node uses `triage_with_supplemental`.

Deterministic rules always run first. An optional supplemental classifier may raise the risk level but cannot lower a deterministic result. A classifier exception falls back to deterministic rules. When safety sets `allow_normal_planning=false`, planning is bypassed.

The original `CarePathWorkflow` also imports the upgraded deterministic `triage_safety`, preserving existing API compatibility while gaining negation-aware rule handling.

## Bounded retries

Verifier regeneration is bounded to one Planner retry. `AgentGraphState.retry_count` is constrained to `0..1`; the route checks the existing verifier audit count so a second regeneration request cannot form a self-loop.

The original `WorkflowConfig` continues to bound tool attempts and verifier regeneration for the synchronous compatibility orchestrator.

## LangGraph node audit schema

Every wrapped LangGraph node emits a `NodeAuditEvent` with:

- node name;
- `started_at` and `finished_at`;
- bounded input summary;
- referenced patient record IDs;
- referenced external document IDs;
- safe structured tool parameters;
- model provider;
- retry count;
- result status (`success`, `blocked`, or `failed`).

### Privacy minimisation

The node audit intentionally does not copy the full request, journal content, retrieved evidence content, model draft, final response or raw exception message. Input summaries contain IDs/counts/booleans only. Tool-parameter keys associated with prompts, messages, notes, text, journal content, secrets, API keys or tokens are removed before the event is stored in state.

This richer LangGraph event schema complements the existing CP-013 persisted reviewer trace. CP-013 remains backward compatible; its database schema and `/audit/{interaction_id}` contract are not silently changed by the LangGraph protocol layer.

## Controlled failures

A node exception becomes `AgentErrorState` with the node, stable failure code and retry count. Raw exception text is excluded. Guarded graph edges route the state to Composer and Feedback Update so the graph terminates normally without returning an unverified plan.

## Upstream contracts

The LangGraph state reuses rather than duplicates:

- deterministic/supplemental conservative safety from `backend.safety`;
- Patient Evidence and Qdrant external evidence from `backend.retrieval`;
- CP-005 deterministic analytics for structured time-series facts;
- CP-013 privacy principles for audit minimisation.

## Focused validation

```bash
pytest tests/test_langgraph_protocol.py tests/test_safety_triage_advanced.py -q
```

Tests cover normal execution, one bounded regeneration, JSON round-trip, safety bypass, controlled node failure, requested audit fields and absence of sensitive raw text from node audit events.
