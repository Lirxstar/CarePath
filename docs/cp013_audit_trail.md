# CP-013 audit trail

CP-013 turns the CP-009 workflow state into a reviewer-readable, ordered audit trace while preserving the privacy constraints in `docs/safety_privacy_spec.md`.

## Event ordering

`backend.audit.build_workflow_audit` walks the workflow's recorded `visited_nodes` and emits canonical `AuditEvent` records in execution order. The supported trace covers:

1. safety triage decision;
2. tool selection/execution metadata;
3. personal and external retrieval references;
4. initial plan generation;
5. verifier disposition;
6. `plan_revised` plus a second verifier event when the bounded regeneration path is used;
7. final response disposition.

Sequence numbers are generated contiguously from 1. `AuditEventTable` already enforces uniqueness for `(interaction_id, sequence_number)`.

## Persistence boundary

The Agent workflow remains database-independent. `/coach/message` first persists and flushes the `InteractionTable` row, then `persist_workflow_audit` writes the complete trace in the same SQLAlchemy transaction. A duplicate trace for the same interaction is rejected rather than silently appended.

`GET /audit/{interaction_id}` continues to read canonical `AuditEvent` rows ordered by `sequence_number`, so the CP-012 HTTP contract becomes the reviewer surface for the CP-013 persisted trace.

## Privacy minimisation

Audit construction uses a fixed allowlist of metadata. It records identifiers, evidence/source references, argument field names, counts, enum values, booleans and controlled failure/rule codes.

It deliberately does **not** copy:

- `request_text` or raw user messages;
- journal or other retrieved content;
- tool argument values or tool result values;
- model drafts, prompts or full model responses;
- free-text plan feedback reasons;
- secrets, credentials or stack traces.

The final response remains available only through the existing permitted `Interaction.response_json` boundary; the audit event records only response/status metadata.

## Automated coverage

`tests/storage/test_audit_trail.py` demonstrates:

- ordering across safety, tool, retrieval, planning, one regeneration, verification and response stages;
- tool/evidence references without raw payload copies;
- persistence into `audit_events` with contiguous sequence numbers;
- rejection of duplicate traces;
- sentinel request, journal, context, tool, evidence, draft, secret and response text never appearing in serialized audit events.

`tests/test_cp012_api_contract.py` additionally verifies that a real `/coach/message` interaction produces an ordered reviewer trace through `/audit/{interaction_id}`.
