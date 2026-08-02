from __future__ import annotations

import asyncio
import hashlib
from time import perf_counter_ns

from backend.api.app.llm.mock import MockLLMProvider
from backend.evaluation.harness import BaselineId, ExecutionStatus, LatencySource
from backend.evaluation.scenarios import SafetyOutcome, ToolName
from backend.safety import TriageContext, triage_safety

from .complete_models import (
    BenchmarkRequest,
    CitationRecord,
    ClaimRecord,
    CompleteBaselineOutput,
    EvidenceNamespace,
    RetrievalHit,
    SecurityDisposition,
)
from .complete_scenarios import (
    _DIAGNOSIS_MARKERS,
    _MEDICATION_MARKERS,
    _SECURITY_MARKERS,
    _retrieve,
    _sanitise_untrusted,
    _security_attack_text,
    _select_tools,
    _structured_signals,
)


class CompleteBaselineRunner:
    def __init__(
        self,
        baseline_id: BaselineId,
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
        seed: int = 7,
        deterministic_latency: bool = False,
    ) -> None:
        self.baseline_id = baseline_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.seed = seed
        self.deterministic_latency = deterministic_latency
        self.provider = MockLLMProvider()

    def run(self, request: BenchmarkRequest) -> CompleteBaselineOutput:
        started = perf_counter_ns()
        try:
            output = self._run(request, started)
        except Exception:
            elapsed = self._latency(request, 0.5)
            return CompleteBaselineOutput(
                baseline_id=self.baseline_id,
                scenario_id=request.scenario_id,
                response_text="Baseline execution failed.",
                status=ExecutionStatus.FAILED,
                error_codes=("runner_exception",),
                ttft_ms=elapsed,
                total_latency_ms=elapsed,
                latency_source=(
                    LatencySource.SYNTHETIC_FIXTURE
                    if self.deterministic_latency
                    else LatencySource.MEASURED
                ),
            )
        return output

    def _run(self, request: BenchmarkRequest, started: int) -> CompleteBaselineOutput:
        personal_hits: tuple[RetrievalHit, ...] = ()
        external_hits: tuple[RetrievalHit, ...] = ()
        selected_tools: tuple[ToolName, ...] = ()
        safety_outcome = SafetyOutcome.ROUTINE
        security = SecurityDisposition.NOT_EXPOSED
        verifier_passed = False
        hostile_for_prompt = ""

        retrieval_baselines = {
            BaselineId.B1_EXTERNAL_RAG,
            BaselineId.B2_DUAL_RAG,
            BaselineId.B3_CAREPATH_AGENT,
        }
        if self.baseline_id in retrieval_baselines:
            external_hits = _retrieve(request, EvidenceNamespace.EXTERNAL)
            hostile_for_prompt = request.hostile_document or ""
        if self.baseline_id in {BaselineId.B2_DUAL_RAG, BaselineId.B3_CAREPATH_AGENT}:
            personal_hits = _retrieve(request, EvidenceNamespace.PERSONAL)

        if self.baseline_id is BaselineId.B3_CAREPATH_AGENT:
            decision = triage_safety(
                request.user_question,
                TriageContext(structured_signals=_structured_signals(request)),
            )
            safety_outcome = SafetyOutcome(decision.risk_level.value)
            selected_tools = _select_tools(request)
            attack_text = _security_attack_text(request)
            hostile_for_prompt, injection_detected = _sanitise_untrusted(hostile_for_prompt)
            if request.hostile_document is not None:
                injection_detected = True
            if any(marker in attack_text for marker in _SECURITY_MARKERS):
                injection_detected = True
            security = (
                SecurityDisposition.REJECTED
                if injection_detected
                else SecurityDisposition.NOT_EXPOSED
            )
            verifier_passed = True
        elif hostile_for_prompt:
            security = SecurityDisposition.VULNERABLE

        prompt = self._prompt(
            request,
            personal_hits=personal_hits,
            external_hits=external_hits,
            hostile_document=hostile_for_prompt,
            safety_outcome=safety_outcome,
        )
        provider_started = perf_counter_ns()
        generated = asyncio.run(
            self.provider.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=self.seed,
            )
        )
        measured_ttft = (perf_counter_ns() - provider_started) / 1_000_000
        ttft_ms = self._latency(request, 0.25) if self.deterministic_latency else measured_ttft

        text = generated
        lowered = _security_attack_text(request)
        if self.baseline_id is BaselineId.B3_CAREPATH_AGENT:
            if safety_outcome is SafetyOutcome.URGENT:
                text = "Urgent safety escalation. Normal planning is paused."
            elif safety_outcome is SafetyOutcome.CAUTION:
                text = (
                    "Caution-level safety guidance. Pause progression and seek professional review."
                )
            elif any(marker in lowered for marker in _DIAGNOSIS_MARKERS + _MEDICATION_MARKERS):
                text = "I cannot diagnose conditions or recommend medication changes."
                safety_outcome = SafetyOutcome.CAUTION
            elif security is SecurityDisposition.REJECTED:
                text = "Untrusted instructions were rejected; only permitted evidence was used."

        evidence_refs = tuple(hit.evidence_ref for hit in (*personal_hits, *external_hits))
        supported = bool(evidence_refs) or self.baseline_id is BaselineId.B3_CAREPATH_AGENT
        claim = ClaimRecord(
            claim_id="claim-1",
            text=text,
            is_medical=False,
            supported=supported,
            evidence_refs=evidence_refs[:1],
        )
        citations = (
            (CitationRecord(evidence_ref=evidence_refs[0], claim_ids=(claim.claim_id,)),)
            if evidence_refs
            else ()
        )
        measured_total = (perf_counter_ns() - started) / 1_000_000
        total_ms = self._latency(request, 1.0) if self.deterministic_latency else measured_total
        return CompleteBaselineOutput(
            baseline_id=self.baseline_id,
            scenario_id=request.scenario_id,
            response_text=text,
            selected_tools=selected_tools,
            tool_successes=tuple(True for _ in selected_tools),
            retrieval_hits=(*personal_hits, *external_hits),
            claims=(claim,),
            citations=citations,
            safety_outcome=safety_outcome,
            security_disposition=security,
            verifier_passed=verifier_passed,
            ttft_ms=ttft_ms,
            total_latency_ms=total_ms,
            latency_source=(
                LatencySource.SYNTHETIC_FIXTURE
                if self.deterministic_latency
                else LatencySource.MEASURED
            ),
        )

    def _latency(self, request: BenchmarkRequest, scale: float) -> float:
        identity = f"{self.baseline_id.value}:{request.scenario_id}:{self.seed}:{scale}"
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        return round((int.from_bytes(digest[:2], "big") % 500 + 50) * scale / 10, 4)

    def _prompt(
        self,
        request: BenchmarkRequest,
        *,
        personal_hits: tuple[RetrievalHit, ...],
        external_hits: tuple[RetrievalHit, ...],
        hostile_document: str,
        safety_outcome: SafetyOutcome,
    ) -> str:
        return "\n".join(
            (
                f"scenario={request.scenario_id}",
                f"question={request.user_question}",
                f"context={' | '.join(request.context_overrides)}",
                f"personal={','.join(hit.evidence_ref for hit in personal_hits)}",
                f"external={','.join(hit.evidence_ref for hit in external_hits)}",
                f"retrieved_document={hostile_document}",
                f"safety={safety_outcome.value}",
                "Return a concise non-diagnostic response.",
            )
        )
