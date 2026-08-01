from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.storage.models import (
    DataImportTable,
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    JournalEntryTable,
    ObservationTable,
    PlanActionTable,
    PlanFeedbackTable,
    UserProfileTable,
)

from .models import ImportIssue, ImportReport, PreparedImport


class ImportService:
    """Persist validated imports atomically and keep import provenance."""

    def persist(self, prepared: PreparedImport, session: Session) -> ImportReport:
        report = prepared.report
        if report.status == "failed":
            self._store_report(report, session)
            session.commit()
            return report

        report.inserted_records = self._count(prepared)
        try:
            with session.begin():
                self._add(UserProfileTable, prepared.user_profiles, session)
                session.flush()

                self._add(GoalTable, prepared.goals, session)
                self._add(ObservationTable, prepared.observations, session)
                self._add(JournalEntryTable, prepared.journal_entries, session)
                self._add(InteractionTable, prepared.interactions, session)
                session.flush()

                self._add(InterventionPlanTable, prepared.intervention_plans, session)
                session.flush()

                self._add(PlanActionTable, prepared.plan_actions, session)
                session.flush()

                self._add(PlanFeedbackTable, prepared.plan_feedback, session)
                session.flush()

                self._add_import_audit(report, session)
            return report
        except Exception:
            session.rollback()
            report.status = "failed"
            report.inserted_records = 0
            report.blocking_errors.append(
                ImportIssue(
                    code="transaction_failed",
                    message="Validated import could not be persisted atomically",
                )
            )
            self._store_report(report, session)
            session.commit()
            return report

    @staticmethod
    def _add_import_audit(report: ImportReport, session: Session) -> None:
        session.add(
            DataImportTable(
                import_id=str(report.import_id),
                source_format=report.source_format,
                source_hash=report.source_hash,
                imported_at=report.imported_at,
                status=report.status,
                received_records=report.received_records,
                inserted_records=report.inserted_records,
                fixed_issues=[item.model_dump(mode="json") for item in report.fixed_issues],
                skipped_records=[item.model_dump(mode="json") for item in report.skipped_records],
                blocking_errors=[item.model_dump(mode="json") for item in report.blocking_errors],
            )
        )

    @staticmethod
    def _store_report(report: ImportReport, session: Session) -> None:
        ImportService._add_import_audit(report, session)

    @staticmethod
    def _add(model: type[Any], records: Iterable[dict[str, object]], session: Session) -> None:
        for record in records:
            values = {key: ImportService._db_value(value) for key, value in record.items()}
            if model is ObservationTable and "metadata" in values:
                values["metadata_json"] = values.pop("metadata")
            session.add(model(**values))

    @staticmethod
    def _db_value(value: object) -> object:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (datetime, date)):
            return value
        if isinstance(value, dict):
            return {str(key): ImportService._json_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [ImportService._json_value(item) for item in value]
        return value

    @staticmethod
    def _json_value(value: object) -> object:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): ImportService._json_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [ImportService._json_value(item) for item in value]
        return value

    @staticmethod
    def _count(prepared: PreparedImport) -> int:
        return sum(
            len(group)
            for group in (
                prepared.user_profiles,
                prepared.observations,
                prepared.journal_entries,
                prepared.goals,
                prepared.interactions,
                prepared.intervention_plans,
                prepared.plan_actions,
                prepared.plan_feedback,
            )
        )
