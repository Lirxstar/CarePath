from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from backend.domain import (
    Goal,
    Interaction,
    InterventionPlan,
    JournalEntry,
    Observation,
    PlanAction,
    PlanFeedback,
    UserProfile,
)
from backend.domain.models import InteractionStatus, Language, RiskLevel

from .models import ImportIssue, ImportReport, PreparedImport
from .validators import content_hash


class JSONHealthImporter:
    """Import the project JSON package into CP-002 canonical records."""

    def prepare(self, data: bytes) -> PreparedImport:
        source_hash = content_hash(data)
        imported_at = datetime.now(UTC)
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._failed(source_hash, imported_at, "invalid_json", str(exc))

        if not isinstance(payload, dict):
            return self._failed(
                source_hash,
                imported_at,
                "invalid_package",
                "JSON root must be object",
            )

        history = payload.get("intervention_history", {})
        if not isinstance(history, dict):
            return self._failed(
                source_hash,
                imported_at,
                "invalid_intervention_history",
                "intervention_history must be object",
            )

        raw_profiles = payload.get(
            "user_profiles",
            payload.get("profiles", payload.get("profile", [])),
        )
        collection_specs: tuple[tuple[str, object, type[Any], bool], ...] = (
            ("UserProfile", raw_profiles, UserProfile, True),
            ("Observation", payload.get("observations", []), Observation, False),
            ("JournalEntry", payload.get("journal_entries", []), JournalEntry, False),
            ("Goal", payload.get("goals", []), Goal, False),
            ("InterventionPlan", history.get("plans", []), InterventionPlan, False),
            ("PlanAction", history.get("actions", []), PlanAction, False),
            ("PlanFeedback", history.get("plan_feedback", []), PlanFeedback, False),
        )

        blocking: list[ImportIssue] = []
        normalized: list[tuple[str, list[object], type[Any]]] = []
        for name, raw_records, model, allow_single_object in collection_specs:
            records = self._collection(raw_records, allow_single_object=allow_single_object)
            if records is None:
                blocking.append(
                    ImportIssue(
                        code="invalid_collection",
                        message=f"{name} collection must be a list",
                        resource_type=name,
                    )
                )
                continue
            normalized.append((name, records, model))

        if blocking:
            return PreparedImport(
                report=ImportReport(
                    status="failed",
                    source_format="json",
                    source_hash=source_hash,
                    imported_at=imported_at,
                    received_records=0,
                    inserted_records=0,
                    blocking_errors=blocking,
                )
            )

        validated: dict[str, list[dict[str, object]]] = {}
        skipped: list[ImportIssue] = []
        received = 0
        for name, records, model in normalized:
            validated[name] = []
            received += len(records)
            for index, record in enumerate(records):
                try:
                    instance = model.model_validate(record)
                except ValidationError as exc:
                    skipped.append(
                        ImportIssue(
                            code="invalid_record",
                            resource_type=name,
                            record_index=index,
                            message=str(exc),
                        )
                    )
                    continue
                validated[name].append(dict(instance.model_dump(mode="python")))

        interactions = self._provenance_interactions(
            validated.get("InterventionPlan", []),
            validated.get("UserProfile", []),
            imported_at,
        )
        return PreparedImport(
            report=ImportReport(
                status="partial" if skipped else "success",
                source_format="json",
                source_hash=source_hash,
                imported_at=imported_at,
                received_records=received,
                inserted_records=0,
                skipped_records=skipped,
            ),
            user_profiles=validated.get("UserProfile", []),
            observations=validated.get("Observation", []),
            journal_entries=validated.get("JournalEntry", []),
            goals=validated.get("Goal", []),
            intervention_plans=validated.get("InterventionPlan", []),
            plan_actions=validated.get("PlanAction", []),
            plan_feedback=validated.get("PlanFeedback", []),
            interactions=interactions,
        )

    @staticmethod
    def _collection(value: object, *, allow_single_object: bool) -> list[object] | None:
        if isinstance(value, list):
            return value
        if allow_single_object and isinstance(value, dict):
            return [value]
        return None

    @staticmethod
    def _provenance_interactions(
        plans: list[dict[str, object]],
        profiles: list[dict[str, object]],
        imported_at: datetime,
    ) -> list[dict[str, object]]:
        languages: dict[str, Language] = {}
        for profile in profiles:
            raw_user_id = profile.get("user_id")
            if raw_user_id is None:
                continue
            raw_language = profile.get("preferred_language", Language.EN)
            language = (
                raw_language if isinstance(raw_language, Language) else Language(str(raw_language))
            )
            languages[str(raw_user_id)] = language

        result: dict[UUID, dict[str, object]] = {}
        for plan in plans:
            raw_interaction_id = plan.get("generation_interaction_id")
            if raw_interaction_id is None:
                continue
            interaction_id = UUID(str(raw_interaction_id))
            if interaction_id in result:
                continue
            user_id = UUID(str(plan["user_id"]))
            interaction = Interaction(
                interaction_id=interaction_id,
                user_id=user_id,
                request_text="Imported project intervention history",
                language=languages.get(str(user_id), Language.EN),
                started_at=imported_at,
                completed_at=imported_at,
                risk_level=RiskLevel.ROUTINE,
                final_status=InteractionStatus.COMPLETED,
                response_json={"source": "project_json_import"},
            )
            result[interaction_id] = dict(interaction.model_dump(mode="python"))
        return list(result.values())

    @staticmethod
    def _failed(
        source_hash: str,
        imported_at: datetime,
        code: str,
        message: str,
    ) -> PreparedImport:
        return PreparedImport(
            report=ImportReport(
                status="failed",
                source_format="json",
                source_hash=source_hash,
                imported_at=imported_at,
                received_records=0,
                inserted_records=0,
                blocking_errors=[ImportIssue(code=code, message=message)],
            )
        )
