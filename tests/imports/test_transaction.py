from datetime import UTC, datetime
from pathlib import Path

from backend.imports.fhir import FHIRBundleImporter
from backend.imports.models import ImportIssue, ImportReport, PreparedImport
from backend.imports.service import ImportService
from backend.storage.models import (
    DataImportTable,
    GoalTable,
    InteractionTable,
    InterventionPlanTable,
    ObservationTable,
    PlanActionTable,
    UserProfileTable,
)

FHIR_FIXTURES = Path(__file__).parents[2] / "data" / "examples" / "fhir"


def failed_report(source_format: str, source_hash: str, issue: ImportIssue) -> ImportReport:
    return ImportReport(
        status="failed",
        source_format=source_format,
        source_hash=source_hash,
        imported_at=datetime.now(UTC),
        received_records=0,
        inserted_records=0,
        blocking_errors=[issue],
    )


def test_failed_validation_only_stores_audit(database_session) -> None:
    prepared = PreparedImport(
        report=failed_report(
            "json",
            "a" * 64,
            ImportIssue(code="invalid_collection", message="bad collection"),
        )
    )

    report = ImportService().persist(prepared, database_session)

    assert report.status == "failed"
    assert report.inserted_records == 0
    assert database_session.query(DataImportTable).count() == 1


def test_failed_import_does_not_create_domain_records(database_session) -> None:
    prepared = PreparedImport(
        report=failed_report(
            "fhir",
            "b" * 64,
            ImportIssue(code="invalid_bundle", message="broken bundle"),
        ),
        user_profiles=[{"user_id": "44444444-4444-4444-4444-444444444444"}],
    )

    report = ImportService().persist(prepared, database_session)

    assert report.status == "failed"
    assert database_session.query(DataImportTable).count() == 1
    assert database_session.query(UserProfileTable).count() == 0


def test_valid_fhir_import_persists_atomically_with_audit(database_session) -> None:
    data = (FHIR_FIXTURES / "valid_bundle.json").read_bytes()
    prepared = FHIRBundleImporter().prepare(data)

    report = ImportService().persist(prepared, database_session)

    assert report.status == "success", report.blocking_errors
    assert report.inserted_records == 6
    assert database_session.query(UserProfileTable).count() == 1
    assert database_session.query(ObservationTable).count() == 1
    assert database_session.query(GoalTable).count() == 1
    assert database_session.query(InteractionTable).count() == 1
    assert database_session.query(InterventionPlanTable).count() == 1
    assert database_session.query(PlanActionTable).count() == 1
    audit = database_session.query(DataImportTable).one()
    assert audit.status == "success"
    assert audit.inserted_records == 6
    assert audit.source_hash == report.source_hash


def test_duplicate_persistence_rolls_back_domain_writes_and_records_failure(
    database_session,
) -> None:
    data = (FHIR_FIXTURES / "valid_bundle.json").read_bytes()
    service = ImportService()

    first = service.persist(FHIRBundleImporter().prepare(data), database_session)
    second = service.persist(FHIRBundleImporter().prepare(data), database_session)

    assert first.status == "success", first.blocking_errors
    assert second.status == "failed"
    assert second.inserted_records == 0
    assert second.blocking_errors[-1].code == "transaction_failed"
    assert database_session.query(UserProfileTable).count() == 1
    assert database_session.query(ObservationTable).count() == 1
    assert database_session.query(DataImportTable).count() == 2
