"""Deterministic citation-scope checks layered on the CP-011 verifier."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .verifier import (
    GroundingSafetyVerifier,
    VerificationResult,
    VerificationStatus,
    VerifierState,
)

if TYPE_CHECKING:
    from backend.agents.workflow import VerificationDisposition

_CITATION_FIX = (
    "replace the citation with retrieved evidence from the same claim domain or rewrite the claim"
)
_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "sleep": ("sleep", "bed", "wake", "insomnia", "睡", "眠"),
    "activity": (
        "walk",
        "step",
        "exercise",
        "activity",
        "movement",
        "运动",
        "步",
        "運動",
        "歩",
    ),
    "stress_mood": (
        "stress",
        "mood",
        "breathing",
        "calming",
        "压力",
        "情绪",
        "ストレス",
        "気分",
    ),
    "falls": ("fall", "balance", "trip", "hazard", "跌倒", "平衡", "転倒", "バランス"),
}


class StrictGroundingSafetyVerifier:
    """Production verifier adding citation-domain support and sanitizer audit flags."""

    def __init__(self, base: GroundingSafetyVerifier | None = None) -> None:
        self.base = base or GroundingSafetyVerifier()

    def __call__(self, state: VerifierState) -> VerificationDisposition:
        from backend.agents.workflow import VerificationDisposition

        result = self.verify(state)
        return VerificationDisposition(result.status.value)

    def verify(self, state: VerifierState) -> VerificationResult:
        result = self.base.verify(state)
        injection_detected = bool(state.context.get("prompt_injection_detected"))
        failed_rule_ids = list(result.failed_rule_ids)
        required_fixes = list(result.required_fixes)

        if result.status is VerificationStatus.PASS and _has_mismatched_general_citation(state):
            failed_rule_ids.append("VER-GROUND-005")
            required_fixes.append(_CITATION_FIX)

        if failed_rule_ids and result.status is VerificationStatus.PASS:
            status = (
                VerificationStatus.REGENERATE_ONCE
                if state.regeneration_count == 0
                else VerificationStatus.FALLBACK
            )
        else:
            status = result.status

        updated = result.model_copy(
            update={
                "status": status,
                "failed_rule_ids": failed_rule_ids,
                "required_fixes": required_fixes,
                "prompt_injection_detected": (
                    result.prompt_injection_detected or injection_detected
                ),
            }
        )
        _update_latest_audit(state, updated)
        return updated


def _has_mismatched_general_citation(state: VerifierState) -> bool:
    draft = state.draft or {}
    claims = draft.get("claims")
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes, bytearray)):
        return False

    external: dict[str, str] = {}
    for item in state.external_evidence:
        external[item.evidence_id] = item.content
        if item.source_id:
            external[item.source_id] = item.content

    for raw_claim in claims:
        if not isinstance(raw_claim, Mapping):
            continue
        kind = str(raw_claim.get("kind", raw_claim.get("claim_type", ""))).lower()
        if kind not in {"general", "general_health", "guideline", "health_behaviour"}:
            continue
        statement = raw_claim.get("statement")
        refs = raw_claim.get("evidence_ids", raw_claim.get("citation_ids", ()))
        if not isinstance(statement, str):
            continue
        ref_values: tuple[str, ...]
        if isinstance(refs, str):
            ref_values = (refs,)
        elif isinstance(refs, Sequence):
            ref_values = tuple(item for item in refs if isinstance(item, str))
        else:
            ref_values = ()
        contents = [external[ref] for ref in ref_values if ref in external]
        if not contents:
            continue
        claim_domains = _domains(statement)
        if not claim_domains:
            continue
        evidence_domains = set().union(*(_domains(content) for content in contents))
        if claim_domains.isdisjoint(evidence_domains):
            return True
    return False


def _domains(text: str) -> set[str]:
    lowered = text.casefold()
    return {
        domain
        for domain, terms in _DOMAIN_TERMS.items()
        if any(term.casefold() in lowered for term in terms)
    }


def _update_latest_audit(state: VerifierState, result: VerificationResult) -> None:
    trace = state.context.get("audit_trace")
    if not isinstance(trace, list) or not trace:
        return
    latest = trace[-1]
    if not isinstance(latest, dict) or latest.get("event_type") != "verification":
        return
    summary = latest.get("output_summary")
    if not isinstance(summary, dict):
        return
    summary["status"] = result.status.value
    summary["failed_rule_ids"] = list(result.failed_rule_ids)
    summary["verification_passed"] = result.status is VerificationStatus.PASS
    summary["prompt_injection_detected"] = result.prompt_injection_detected
