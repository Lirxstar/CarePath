from __future__ import annotations

import hashlib

from backend.safety import triage_safety

from .harness import (
    BaselineId,
    BaselineOutput,
    CitationRecord,
    EvaluationClaim,
    LatencySource,
    ToolExecution,
)
from .scenarios import EvaluationScenario, SafetyOutcome


_BASE_LATENCY_MS = {
    BaselineId.B0_LLM_ONLY: 40.0,
    BaselineId.B1_EXTERNAL_RAG: 70.0,
    BaselineId.B2_DUAL_RAG: 95.0,
    BaselineId.B3_CAREPATH_AGENT: 140.0,
}


class ReferenceBaselineRunner:
    """Deterministic fixture runner for validating the evaluation pipeline itself.

    Generated records are marked as synthetic fixtures. They are not model benchmark
    results and must not be used for CP-018 threshold claims.
    """

    def __init__(self, baseline_id: BaselineId) -> None:
        self.baseline_id = baseline_id

    def run(self, scenario: EvaluationScenario) -> BaselineOutput:
        include_external = self.baseline_id in {
            BaselineId.B1_EXTERNAL_RAG,
            BaselineId.B2_DUAL_RAG,
            BaselineId.B3_CAREPATH_AGENT,
        }
        include_personal = self.baseline_id in {
            BaselineId.B2_DUAL_RAG,
            BaselineId.B3_CAREPATH_AGENT,
        }
        include_tools = self.baseline_id is BaselineId.B3_CAREPATH_AGENT

        personal_evidence = scenario.expected_evidence.personal if include_personal else ()
        external_evidence = scenario.expected_evidence.external if include_external else ()
        evidence_refs = personal_evidence + external_evidence
        selected_tools = scenario.expected_tools if include_tools else ()
        claim = EvaluationClaim(
            claim_id="summary-claim",
            text=f"Reference fixture response for {scenario.scenario_id}.",
            is_medical=False,
            supported=bool(evidence_refs),
            evidence_refs=evidence_refs,
        )
        citations = tuple(
            CitationRecord(
                citation_id=f"citation-{index:02d}",
                evidence_ref=evidence_ref,
                supports_claim_ids=(claim.claim_id,),
            )
            for index, evidence_ref in enumerate(evidence_refs, start=1)
        )
        decision = triage_safety(scenario.user_question)
        safety_outcome = SafetyOutcome(decision.risk_level.value)

        return BaselineOutput(
            baseline_id=self.baseline_id,
            scenario_id=scenario.scenario_id,
            response_text=claim.text,
            selected_tools=selected_tools,
            tool_executions=tuple(
                ToolExecution(tool_name=tool_name, success=True)
                for tool_name in selected_tools
            ),
            personal_evidence=personal_evidence,
            external_evidence=external_evidence,
            claims=(claim,),
            citations=citations,
            safety_outcome=safety_outcome,
            latency_ms=self._latency_ms(scenario.scenario_id),
            latency_source=LatencySource.SYNTHETIC_FIXTURE,
        )

    def _latency_ms(self, scenario_id: str) -> float:
        digest = hashlib.sha256(
            f"{self.baseline_id.value}:{scenario_id}".encode()
        ).digest()
        return _BASE_LATENCY_MS[self.baseline_id] + float(digest[0] % 17)


def reference_runners() -> tuple[ReferenceBaselineRunner, ...]:
    return tuple(ReferenceBaselineRunner(baseline_id) for baseline_id in BaselineId)
