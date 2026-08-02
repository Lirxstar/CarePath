from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import cast

from backend.evaluation.harness import BaselineId

from .complete_models import ScoredResult

_TARGETS = {
    "citation_precision_min": 0.85,
    "patient_context_fidelity_min": 0.90,
    "tool_selection_accuracy_min": 0.90,
    "unsupported_claim_rate_max": 0.10,
}

_MANUAL_REVIEW_GROUPS: dict[str, tuple[str, ...]] = {
    "retrieval_and_planning": (
        "CP016-RT-001",
        "CP016-RT-004",
        "CP016-RT-006",
        "CP016-RT-012",
        "CP016-RT-014",
        "CP016-RT-015",
        "CP016-TR-002",
        "CP016-TR-004",
        "CP016-TR-005",
        "CP016-TR-007",
        "CP016-MC-007",
        "CP016-HI-001",
        "CP016-ML-003",
    ),
    "planning": (
        "CP016-RT-002",
        "CP016-RT-003",
        "CP016-RT-009",
        "CP016-RT-010",
        "CP016-RT-005",
        "CP016-RT-011",
        "CP016-RT-013",
        "CP016-ML-001",
        "CP016-TR-001",
        "CP016-TR-006",
        "CP016-TR-008",
        "CP016-MC-001",
        "CP016-MC-002",
        "CP016-MC-006",
        "CP016-MC-008",
        "CP016-ML-002",
    ),
    "retrieval": ("CP016-RT-016", "CP016-HI-002"),
    "citation": (),
    "annotation": (),
}


def build_low_score_review(results: Sequence[ScoredResult]) -> dict[str, object]:
    reviewed = {scenario for values in _MANUAL_REVIEW_GROUPS.values() for scenario in values}
    current: list[dict[str, object]] = []
    for result in results:
        if result.output.baseline_id is not BaselineId.B3_CAREPATH_AGENT:
            continue
        metrics = result.metrics
        categories: list[str] = []
        if metrics.retrieval_applicable and metrics.patient_context_fidelity < 0.90:
            categories.append("retrieval")
        if metrics.tool_routing_applicable and metrics.tool_selection_accuracy < 0.90:
            categories.append("planning")
        if metrics.citation_applicable and metrics.citation_precision < 0.85:
            categories.append("citation")
        if metrics.citation_applicable and metrics.unsupported_claim_rate > 0.10:
            categories.append("planning")
        if not categories:
            continue
        current.append(
            {
                "scenario_id": result.output.scenario_id,
                "categories": list(dict.fromkeys(categories)),
                "review_status": "reviewed"
                if result.output.scenario_id in reviewed
                else "unreviewed",
                "metrics": {
                    "patient_context_fidelity": metrics.patient_context_fidelity,
                    "tool_selection_accuracy": metrics.tool_selection_accuracy,
                    "citation_precision": metrics.citation_precision,
                    "unsupported_claim_rate": metrics.unsupported_claim_rate,
                },
            }
        )
    statuses = Counter(str(item["review_status"]) for item in current)
    return {
        "review_method": "manual scenario review with deterministic report generation",
        "targets": dict(_TARGETS),
        "root_cause_taxonomy": ["retrieval", "planning", "citation", "annotation"],
        "historical_review_groups": {
            key: list(value) for key, value in _MANUAL_REVIEW_GROUPS.items()
        },
        "historical_reviewed_count": len(reviewed),
        "historical_findings": {
            "retrieval": (
                "Context Builder records were available but not all were represented "
                "in scored patient evidence."
            ),
            "planning": (
                "The router ignored supplied context or treated generic plan and routine "
                "wording as adherence intent."
            ),
            "citation": "No confirmed citation defect in the reviewed schema-2.2 artifact.",
            "annotation": "No remaining annotation defect after fixture and stable-ID alignment.",
        },
        "current_low_score_count": len(current),
        "current_reviewed_count": statuses["reviewed"],
        "unreviewed_current_low_score_count": statuses["unreviewed"],
        "current_low_scores": current,
    }


def render_low_score_review_markdown(report: dict[str, object]) -> str:
    lines = [
        "# B3 low-score manual review",
        "",
        (
            "This report distinguishes retrieval, planning and tool routing, citation, "
            "and annotation causes."
        ),
        "",
        f"- Historical reviewed scenarios: {report['historical_reviewed_count']}",
        f"- Current low-score scenarios: {report['current_low_score_count']}",
        f"- Unreviewed current low-score scenarios: {report['unreviewed_current_low_score_count']}",
        "",
        "| Scenario | Categories | Status |",
        "|---|---|---|",
    ]
    current = cast(list[dict[str, object]], report["current_low_scores"])
    for item in current:
        categories = cast(list[str], item["categories"])
        lines.append(
            f"| {item['scenario_id']} | {', '.join(categories)} | {item['review_status']} |"
        )
    if not report["current_low_scores"]:
        lines.append("| none | none | all current targets met |")
    return "\n".join(lines) + "\n"
