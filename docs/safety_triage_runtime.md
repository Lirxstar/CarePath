# Safety Triage runtime contract

This document records the executable safety additions layered on the normative `docs/safety_privacy_spec.md`.

## Deterministic first

`backend.safety.triage_safety` always evaluates application-controlled rule tables before normal coaching. It returns the canonical `TriageDecision` fields:

- `routine`, `caution`, or `urgent` risk;
- matched rule IDs;
- policy flags;
- whether normal planning is allowed;
- required response actions;
- uncertainty when applicable.

Urgent and caution decisions bypass ordinary planning under the existing workflow contract.

## Explicit negation

Text-rule matches are checked for explicit nearby negation before a rule is accepted. Examples such as:

```text
I do not have face droop.
I do not have a suicide plan.
```

must not be escalated solely because the negated phrase contains a red-flag keyword.

Negation handling is deliberately local and conservative. It does not suppress a phrase whose negation is itself the danger signal, for example:

```text
I am not breathing.
```

Structured safety signals are never cancelled by free-text negation.

## Supplemental model boundary

`triage_with_supplemental` optionally accepts a `SupplementalSafetyClassifier`. Its only allowed output is a bounded `SupplementalSafetyAssessment` containing a risk level and reason codes. The classifier does not diagnose, prescribe, choose emergency resources, or override system policy.

Merge policy is monotonic:

```text
deterministic urgent + model routine  -> urgent
deterministic caution + model routine -> caution
deterministic routine + model caution -> caution
deterministic routine + model urgent  -> urgent
```

Therefore a model may add a conservative escalation but can never downgrade a deterministic result. Classifier failure falls back to the deterministic result.

Supplemental escalations add an auditable `MODEL-*` reason and uncertainty flag. Caution escalation includes professional-assessment guidance; urgent escalation receives the normal urgent response actions.

## Tests

Focused safety tests cover:

- routine health-behaviour requests;
- urgent breathing and other existing CP-008 fixtures;
- explicit negation;
- structured-signal precedence;
- model/rule conflict where the model attempts to downgrade;
- supplemental escalation;
- classifier failure.

Run:

```bash
pytest tests/test_safety_triage.py tests/test_safety_triage_advanced.py -q
```
