"""Negation-aware deterministic triage plus an optional conservative supplemental classifier."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import RiskLevel

from .triage import (
    _RISK_RANK,
    _STRUCTURED_RULES,
    _TEXT_RULES,
    PolicyFlag,
    ResponseAction,
    TriageContext,
    TriageDecision,
    _dedupe,
    _response_actions,
)


class SupplementalSafetyAssessment(BaseModel):
    """Bounded model output: classification metadata only, never diagnosis or advice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_level: RiskLevel
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)


class SupplementalSafetyClassifier(Protocol):
    def __call__(
        self,
        text: str,
        context: TriageContext | None,
    ) -> SupplementalSafetyAssessment: ...


_EN_NEGATION_PREFIX = re.compile(
    r"(?:\b(?:no|not|never|without|deny|denies|denied|denying|"
    r"don't|doesn't|didn't|do not|does not|did not)\b[\w\s,'-]{0,36})$",
    re.IGNORECASE,
)
_EN_NEGATION_SUFFIX = re.compile(
    r"^\s*(?:(?:is|are|was|were)\s+)?(?:absent|not present|denied)\b",
    re.IGNORECASE,
)
_ZH_NEGATION_PREFIX = re.compile(r"(?:没有|并没有|并无|无|不是|未出现|否认).{0,12}$")
_ZH_NEGATION_SUFFIX = re.compile(r"^(?:并不存在|没有|不存在|未出现)")
_JA_NEGATION_PREFIX = re.compile(r"(?:ない|ありません|否定).{0,8}$")
_JA_NEGATION_SUFFIX = re.compile(
    r"^(?:は|が|も|では|じゃ)?(?:ない|ありません|ではありません|じゃない)"
)
_IMPERATIVE_DIAGNOSIS_REQUEST = re.compile(
    r"\bdiagnose\s+(?:me|my|this|the|what|which)\b"
    r"|\bwhat\s+(?:disease|condition|illness)\s+(?:is|could be|might be)\s+"
    r"(?:causing|behind)\b",
    re.IGNORECASE,
)


def triage_safety(text: str, context: TriageContext | None = None) -> TriageDecision:
    """Run deterministic safety rules while suppressing explicitly negated rule matches."""

    if not text.strip():
        raise ValueError("request_text must contain non-whitespace text")

    normalized = " ".join(text.casefold().split())
    matched_rule_ids: list[str] = []
    flags: list[PolicyFlag] = []
    risk_level = RiskLevel.ROUTINE

    for rule in _TEXT_RULES:
        matched = False
        for pattern in rule.patterns:
            for match in pattern.finditer(normalized):
                if not _is_explicitly_negated(normalized, match.start(), match.end()):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            continue
        matched_rule_ids.append(rule.rule_id)
        flags.append(rule.policy_flag)
        if _RISK_RANK[rule.risk_level] > _RISK_RANK[risk_level]:
            risk_level = rule.risk_level

    for match in _IMPERATIVE_DIAGNOSIS_REQUEST.finditer(normalized):
        if _is_explicitly_negated(normalized, match.start(), match.end()):
            continue
        matched_rule_ids.append("TRI-CAU-004")
        flags.append(PolicyFlag.DIAGNOSIS_REQUEST)
        if _RISK_RANK[RiskLevel.CAUTION] > _RISK_RANK[risk_level]:
            risk_level = RiskLevel.CAUTION
        break

    if context is not None:
        for signal in context.structured_signals:
            rule_id, signal_risk, flag = _STRUCTURED_RULES[signal]
            matched_rule_ids.append(rule_id)
            flags.append(flag)
            if _RISK_RANK[signal_risk] > _RISK_RANK[risk_level]:
                risk_level = signal_risk

    if risk_level is RiskLevel.ROUTINE:
        return TriageDecision(risk_level=RiskLevel.ROUTINE, allow_normal_planning=True)

    deduped_flags = _dedupe(flags)
    uncertainty_reason = None
    if PolicyFlag.DATA_QUALITY in deduped_flags or PolicyFlag.UNCERTAINTY in deduped_flags:
        uncertainty_reason = "Safety-relevant data is missing, conflicting, suspect, or ambiguous."
    return TriageDecision(
        risk_level=risk_level,
        matched_rule_ids=_dedupe(matched_rule_ids),
        policy_flags=deduped_flags,
        allow_normal_planning=False,
        required_response_actions=_response_actions(risk_level, deduped_flags),
        uncertainty_reason=uncertainty_reason,
    )


def triage_with_supplemental(
    text: str,
    context: TriageContext | None = None,
    *,
    classifier: SupplementalSafetyClassifier | None = None,
) -> TriageDecision:
    """Merge optional model classification with rules; the more conservative risk always wins."""

    rules = triage_safety(text, context)
    if classifier is None:
        return rules
    try:
        model = classifier(text, context)
    except Exception:
        return rules
    return merge_safety_decisions(rules, model)


def merge_safety_decisions(
    rules: TriageDecision,
    supplemental: SupplementalSafetyAssessment,
) -> TriageDecision:
    """Return a monotonic merge: supplemental output can escalate but never downgrade rules."""

    risk_level = (
        supplemental.risk_level
        if _RISK_RANK[supplemental.risk_level] > _RISK_RANK[rules.risk_level]
        else rules.risk_level
    )
    if risk_level is rules.risk_level:
        return rules

    flags = _dedupe([*rules.policy_flags, PolicyFlag.UNCERTAINTY])
    reason_ids = [*rules.matched_rule_ids]
    if supplemental.reason_codes:
        reason_ids.extend(f"MODEL-{_reason_code(item)}" for item in supplemental.reason_codes)
    else:
        reason_ids.append("MODEL-SUPPLEMENTAL")
    actions = list(_response_actions(risk_level, flags))
    if risk_level is RiskLevel.CAUTION:
        actions.append(ResponseAction.PROFESSIONAL_ASSESSMENT)

    return TriageDecision(
        risk_level=risk_level,
        matched_rule_ids=_dedupe(reason_ids),
        policy_flags=flags,
        allow_normal_planning=False,
        required_response_actions=_dedupe(actions),
        uncertainty_reason=(
            rules.uncertainty_reason
            or "Supplemental safety classification raised a more conservative risk level."
        ),
    )


def _reason_code(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").upper()
    return normalized[:64] or "UNSPECIFIED"


def _is_explicitly_negated(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 48) : start]
    suffix = text[end : min(len(text), end + 28)]
    return any(
        pattern.search(prefix) is not None
        for pattern in (_EN_NEGATION_PREFIX, _ZH_NEGATION_PREFIX, _JA_NEGATION_PREFIX)
    ) or any(
        pattern.search(suffix) is not None
        for pattern in (_EN_NEGATION_SUFFIX, _ZH_NEGATION_SUFFIX, _JA_NEGATION_SUFFIX)
    )


SafetyClassifierFactory = Callable[[], SupplementalSafetyClassifier]

__all__ = [
    "SafetyClassifierFactory",
    "SupplementalSafetyAssessment",
    "SupplementalSafetyClassifier",
    "merge_safety_decisions",
    "triage_safety",
    "triage_with_supplemental",
]
