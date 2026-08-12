from __future__ import annotations

from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.domain.models import Language, MetricType
from backend.retrieval import (
    ExternalEvidenceFilters,
    ExternalEvidenceHit,
    PatientEvidenceQuery,
    PatientEvidenceResponse,
    PatientEvidenceService,
)
from backend.retrieval.guidelines.models import GuidelineTopic

from .access import ensure_user_access
from .errors import CarePathError
from .evidence_runtime import ExternalEvidenceSearchIndex, get_external_evidence_index
from .session_scope import get_request_session

router = APIRouter(prefix="/evidence", tags=["evidence"])
SessionDependency = Annotated[Session, Depends(get_request_session)]


def _external_index(request: Request) -> ExternalEvidenceSearchIndex:
    return get_external_evidence_index(request)


@router.get(
    "/external/search",
    response_model=list[ExternalEvidenceHit],
    summary="Search the versioned external guideline evidence index",
)
def search_external_evidence(
    request: Request,
    query: Annotated[str, Query(min_length=1, max_length=500)],
    top_k: Annotated[int, Query(ge=1, le=20)] = 5,
    topics: Annotated[list[GuidelineTopic] | None, Query()] = None,
    language: Language | None = None,
    organisation: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    updated_from: date | None = None,
    updated_to: date | None = None,
) -> list[ExternalEvidenceHit]:
    index = _external_index(request)
    try:
        hits = index.search(
            query,
            top_k=top_k,
            filters=ExternalEvidenceFilters(
                topics=tuple(topics or ()),
                language=language,
                organisation=organisation,
                updated_from=updated_from,
                updated_to=updated_to,
            ),
        )
    except ValueError as exc:
        raise CarePathError(
            "invalid_evidence_search",
            str(exc),
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc
    except Exception as exc:
        raise CarePathError(
            "evidence_search_unavailable",
            "External guideline evidence is temporarily unavailable",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc
    return list(hits)


@router.get(
    "/patient/search",
    response_model=PatientEvidenceResponse,
    summary="Build user-scoped Patient Evidence with bounded time controls",
)
def search_patient_evidence(
    request: Request,
    user_id: UUID,
    session: SessionDependency,
    window_days: Annotated[int | None, Query(ge=7, le=30)] = 7,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    metric_types: Annotated[list[MetricType] | None, Query()] = None,
    keyword: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> PatientEvidenceResponse:
    ensure_user_access(request, session, user_id)
    if window_days not in {None, 7, 30}:
        raise CarePathError(
            "invalid_patient_evidence_window",
            "window_days must be either 7 or 30",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    validated_window_days = cast(Literal[7, 30] | None, window_days)
    resolved_window_days = None if start_at is not None else validated_window_days
    if start_at is not None and end_at is None:
        raise CarePathError(
            "invalid_patient_evidence_window",
            "Explicit start_at requires end_at",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    try:
        query = PatientEvidenceQuery(
            user_id=user_id,
            window_days=resolved_window_days,
            start_at=start_at,
            end_at=end_at,
            metric_types=tuple(metric_types or ()),
            keyword=keyword,
        )
        return PatientEvidenceService(session).retrieve(query)
    except ValueError as exc:
        message = str(exc)
        status = (
            HTTPStatus.NOT_FOUND
            if "profile does not exist" in message
            else HTTPStatus.UNPROCESSABLE_ENTITY
        )
        code = (
            "profile_not_found"
            if status is HTTPStatus.NOT_FOUND
            else "invalid_patient_evidence_query"
        )
        raise CarePathError(code, message, status_code=status) from exc
