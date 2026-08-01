# CP-011 Grounding and Safety Verifier

CP-011 implements the deterministic verification gate between the Intervention Planner and Response Composer in the frozen CarePath workflow.

## Purpose

Planner/model output remains `T5_MODEL_DRAFT` until this verifier passes it. The verifier does not ask a model to judge itself. It applies deterministic safety, grounding, data-quality, injection, and privacy checks derived from `docs/safety_privacy_spec.md` section 12.

## Result contract

`GroundingSafetyVerifier.verify(state)` returns `VerificationResult`:

```json
{
  "status": "pass | regenerate_once | fallback",
  "failed_rule_ids": ["VER-..."],
  "required_fixes": ["bounded controlled fix description"],
  "risk_level": "routine | caution | urgent",
  "prompt_injection_detected": false
}
```

The callable interface returns the existing `VerificationDisposition` so it plugs directly into `CarePathWorkflow`.

A failing first draft requests exactly one regeneration. If the regenerated draft still fails, the verifier returns `fallback`. The CP-009 workflow already enforces `max_regenerations <= 1`, so no third planner generation is possible.

## Checks

The implementation covers the normative verifier rules:

- `VER-SAFE-001`: definitive diagnosis and user-specific disease probability;
- `VER-SAFE-002`: medication start/stop/dose/timing/substitution advice;
- `VER-SAFE-003`: triage risk downgrade or explicit downplaying;
- `VER-SAFE-004`: ordinary seven-day coaching plan on an urgent path;
- `VER-SAFE-005`: activity contradicting an explicit professional restriction;
- `VER-GROUND-001`: missing or unavailable external support for material general claims;
- `VER-GROUND-002`: journal/self-report used as authoritative general medical evidence;
- `VER-GROUND-003`: unavailable/mismatched tool or observation support and unacknowledged material data-quality conflicts;
- `VER-GROUND-004`: user-specific medical causal language;
- `VER-INJ-001`: hostile retrieved instructions used as evidence or reproduced as instructions;
- `VER-INJ-002`: secret-like output or system-prompt disclosure.

## Structured grounding convention

For deterministic claim-level verification, planner drafts may include a `claims` list. Each claim can provide:

```json
{
  "claim_id": "claim-1",
  "kind": "general_health | personal_observation | interpretation",
  "statement": "...",
  "evidence_ids": ["external:chunk-id"],
  "tool_call_id": "trend-1",
  "tool_field": "direction",
  "value": "down"
}
```

General health/behaviour claims require eligible external evidence. Personal observations can instead be supported by personal evidence IDs or deterministic tool outputs. A claim that asserts a specific tool field/value is checked against the actual tool result.

The canonical `evidence` response section is also recognized. Its `supports` claim IDs must exist, and its source/chunk reference must be present in retrieved external evidence.

## Conflicts and uncertainty

When `context` reports material `contradictions`, `conflicts`, `data_quality_issues`, `missingness`, or `material_conflicts`, the draft must preserve uncertainty. Silently converting conflicting/missing data into a confident conclusion fails `VER-GROUND-003`.

## Prompt injection

Instruction-like retrieved chunks are detected only as an additional safety signal; detection is not the security boundary. Such chunks cannot support claims. The verifier records `prompt_injection_detected=true` while keeping the hostile payload itself out of the audit summary.

## Audit trace

Every verifier invocation appends a bounded event to `state.context["audit_trace"]`:

- `event_type=verification`;
- input references: draft attempt number, evidence IDs, tool call IDs;
- output summary: disposition, failed rule IDs, preserved risk level, pass flag, prompt-injection flag.

Raw user questions, journal text, evidence content, model prompts, model completions, and secrets are not copied into the verifier audit event. This keeps the event compatible with the canonical `AuditEvent` privacy boundary and allows a later persistence/API layer to store the trace without reconstructing hidden prompts.

## Automated acceptance coverage

`tests/test_grounding_safety_verifier.py` covers:

1. grounded pass;
2. diagnosis prohibition;
3. medication prohibition;
4. risk downgrade and urgent-plan prohibition;
5. professional activity restriction;
6. missing/unknown citation;
7. journal trust boundary;
8. tool-result contradiction;
9. material conflict without uncertainty;
10. causal medical statement;
11. hostile retrieved instruction;
12. secret-like output;
13. first failure -> one regeneration -> second failure -> controlled fallback with two audit decisions and no third generation.
