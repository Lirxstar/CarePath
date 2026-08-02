from __future__ import annotations

from types import MappingProxyType
from typing import Final

from .complete_models import AggregateMetrics

QUALITY_THRESHOLDS: Final = MappingProxyType(
    {
        "recall_at_5_min": 0.80,
        "mrr_min": 0.90,
        "gold_evidence_coverage_min": 0.75,
        "citation_precision_min": 0.95,
        "evidence_supported_claim_rate_min": 0.95,
        "patient_context_fidelity_min": 0.90,
        "tool_selection_accuracy_min": 0.90,
        "tool_success_min": 1.0,
        "unmapped_evidence_rate_max": 0.0,
        "unsupported_claim_rate_max": 0.0,
        "contradiction_rate_max": 0.0,
    }
)


def evaluate_quality_thresholds(metrics: AggregateMetrics) -> tuple[str, ...]:
    failures: list[str] = []
    minimums = (
        ("recall_at_5", metrics.recall_at_5),
        ("mrr", metrics.mrr),
        ("gold_evidence_coverage", metrics.gold_evidence_coverage),
        ("citation_precision", metrics.citation_precision),
        ("evidence_supported_claim_rate", metrics.evidence_supported_claim_rate),
        ("patient_context_fidelity", metrics.patient_context_fidelity),
        ("tool_selection_accuracy", metrics.tool_selection_accuracy),
        ("tool_success", metrics.tool_success),
    )
    for metric_name, observed in minimums:
        threshold = QUALITY_THRESHOLDS[f"{metric_name}_min"]
        if observed < threshold:
            failures.append(f"b3_{metric_name}_below_{_label(threshold)}")

    maximums = (
        ("unmapped_evidence_rate", metrics.unmapped_evidence_rate),
        ("unsupported_claim_rate", metrics.unsupported_claim_rate),
        ("contradiction_rate", metrics.contradiction_rate),
    )
    for metric_name, observed in maximums:
        threshold = QUALITY_THRESHOLDS[f"{metric_name}_max"]
        if observed > threshold:
            failures.append(f"b3_{metric_name}_above_{_label(threshold)}")
    return tuple(failures)


def observed_quality_metrics(metrics: AggregateMetrics) -> dict[str, float]:
    return {
        "recall_at_5": metrics.recall_at_5,
        "mrr": metrics.mrr,
        "gold_evidence_coverage": metrics.gold_evidence_coverage,
        "citation_precision": metrics.citation_precision,
        "evidence_supported_claim_rate": metrics.evidence_supported_claim_rate,
        "patient_context_fidelity": metrics.patient_context_fidelity,
        "tool_selection_accuracy": metrics.tool_selection_accuracy,
        "tool_success": metrics.tool_success,
        "unmapped_evidence_rate": metrics.unmapped_evidence_rate,
        "unsupported_claim_rate": metrics.unsupported_claim_rate,
        "contradiction_rate": metrics.contradiction_rate,
    }


def _label(value: float) -> str:
    return str(value).replace(".", "_")
