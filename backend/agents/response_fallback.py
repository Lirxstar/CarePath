"""Structured fail-closed responses for workflow paths that cannot return a plan."""

from __future__ import annotations

from backend.domain.models import RiskLevel

from .response_composer import ResponseComposer, ResponseStatement, StructuredCoachResponse


def controlled_failure_response(
    *,
    risk_level: RiskLevel,
    language: str,
    verification_failed: bool = False,
) -> StructuredCoachResponse:
    reason = (
        "CarePath could not verify the generated coaching draft, so the draft was not returned."
        if verification_failed
        else (
            "CarePath could not complete the required data, retrieval, tool, or model "
            "checks safely."
        )
    )
    response = StructuredCoachResponse(
        language=language if language in {"en", "zh", "ja"} else "en",
        risk_level=risk_level,
        what_i_noticed=(
            ResponseStatement(
                statement_id="noticed-1",
                text="The interaction did not complete all required checks.",
            ),
        ),
        what_the_evidence_suggests=(
            ResponseStatement(
                statement_id="evidence-1",
                text="No unverified evidence conclusion is returned on this path.",
            ),
        ),
        realistic_plan_for_this_week=(),
        when_to_seek_professional_help=(
            "Seek appropriate professional help if the concern is persistent, worsening, "
            "or safety-related.",
        ),
        sources=(),
        what_i_am_uncertain_about=(reason,),
        rendered_text="placeholder",
    )
    return response.model_copy(update={"rendered_text": ResponseComposer._render(response)})
