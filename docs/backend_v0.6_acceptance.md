# CarePath backend v0.6 acceptance gate

Backend v0.6 freezes the pre-mobile agent response boundary after Context Builder,
Tool Router, deterministic tools, dual retrieval, Planner, Verifier and audit integration.

## End-to-end order

```text
request
→ Safety Triage
→ Context Builder
→ Tool Router
→ deterministic tools
→ Patient Evidence retrieval
→ External Evidence retrieval
→ Planner
→ strict Grounding & Safety Verifier
→ structured Response Composer
→ audit persistence
```

The workflow remains bounded. A verifier failure can regenerate the plan exactly once.
A second failure returns a controlled structured fallback; there is no autonomous loop.

## Grounding and safety

The production verifier preserves CP-011 checks for diagnosis, medication changes, risk
downgrades, professional restrictions, unsupported references, user/tool contradictions,
causal medical language, prompt injection and secret-like output. v0.6 adds a citation-domain
check so a real but unrelated retrieved chunk cannot satisfy a general behavioural claim.

Every verifier decision records bounded rule IDs and reference IDs in the audit trail. Raw
questions, journal text, evidence bodies, model prompts, exception bodies and secrets are not
copied into audit events.

## Response contract

`POST /coach/message` returns both `response_text` and `structured_response`.
`structured_response` always exposes these six frontend-renderable sections:

1. `what_i_noticed`
2. `what_the_evidence_suggests`
3. `realistic_plan_for_this_week`
4. `when_to_seek_professional_help`
5. `sources`
6. `what_i_am_uncertain_about`

User-data citations and external-guideline citations are separate types. User citations retain
record IDs. Guideline citations retain the exact source ID, chunk ID and display citation.
Response validation rejects unresolved citation IDs or source objects that claim to support an
unknown response item.

Routine, blocked-safety and controlled-failure responses use the same structural contract.
English, Chinese and Japanese rendering preserve the same risk disposition and safety action.

## Prompt-injection and authorization boundary

Retrieved natural-language content is wrapped as untrusted evidence data. The sanitizer marks
and excludes instruction-like spans covering policy override, safety/verifier bypass, secret
exfiltration, tool execution, scope/user override, cross-user access, database execution and
arbitrary URL requests.

Detection is defence in depth. Security still relies on deterministic triage, fixed user scope,
separate personal/external namespaces, allow-listed tools, typed argument validation, bounded
ranges and the verifier. Natural-language content cannot create a new tool, alter the user ID,
construct SQL, request an arbitrary URL, disable Safety Triage or disable the Verifier.

## Automated Gate

`tests/test_backend_v06_gate.py` covers:

- normal coaching;
- data insufficiency;
- empty external retrieval;
- urgent safety escalation;
- tool failure;
- model-node timeout;
- retrieval failure;
- verifier second failure after exactly one rewrite;
- ordered `/audit/{interaction_id}` replay;
- three consecutive successful runs of the primary user story.

`tests/test_prompt_injection_security_v06.py` includes eight explicit attack payloads plus
cross-user tool arguments, arbitrary tool attempts and safety-downgrade attempts.

`tests/test_response_composer_v06.py` verifies the six-section response schema, exact citation
resolution, pseudo-citation rejection and multilingual safety invariance.

`tests/test_strict_grounding_verifier_v06.py` verifies that a known but wrong-domain citation is
rejected and that sanitizer detection is retained as audit-safe verifier metadata.

Repository quality CI remains the release Gate: Ruff format, Ruff lint, strict mypy, pytest with
branch coverage threshold, and frontend quality must all pass before this milestone is merged.
