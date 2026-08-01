from backend.imports.csv_importer import CSVHealthImporter

HEADERS = (
    "observation_id,user_id,metric_type,value_numeric,value_boolean,unit,"
    "observed_at,source_type,quality_flag,confidence,metadata"
)


def csv_row(**overrides: str) -> bytes:
    values = {
        "observation_id": "11111111-1111-1111-1111-111111111111",
        "user_id": "22222222-2222-2222-2222-222222222222",
        "metric_type": "steps",
        "value_numeric": "7200",
        "value_boolean": "",
        "unit": "count",
        "observed_at": "2026-07-28T08:00:00+09:00",
        "source_type": "wearable",
        "quality_flag": "valid",
        "confidence": "0.9",
        "metadata": "{}",
    }
    values.update(overrides)
    return (HEADERS + "\n" + ",".join(values.values())).encode()


def append_row(first: bytes, second: bytes) -> bytes:
    return (first.decode() + "\n" + second.decode().split("\n", 1)[1]).encode()


def test_valid_csv_import_normalizes_units() -> None:
    result = CSVHealthImporter().prepare(csv_row())

    assert result.report.status == "success"
    assert any(item.code == "unit_normalized" for item in result.report.fixed_issues)
    assert result.observations[0]["source_type"] == "csv"
    assert result.observations[0]["metadata"] == {"original_source_type": "wearable"}


def test_missing_column_is_blocking() -> None:
    result = CSVHealthImporter().prepare(b"observation_id\nabc")

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "missing_columns"


def test_invalid_encoding_is_blocking() -> None:
    result = CSVHealthImporter().prepare(b"\xff\xfe\xfd")

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "invalid_encoding"


def test_invalid_boolean_is_skipped() -> None:
    result = CSVHealthImporter().prepare(csv_row(value_boolean="maybe"))

    assert result.report.status == "partial"
    assert result.report.skipped_records[0].code == "invalid_record"


def test_duplicate_conflict_is_blocking() -> None:
    content = append_row(csv_row(), csv_row(value_numeric="9000"))
    result = CSVHealthImporter().prepare(content)

    assert result.report.status == "failed"
    assert result.report.blocking_errors[0].code == "conflicting_duplicate"
    assert result.observations == []


def test_identical_duplicate_is_explicitly_skipped() -> None:
    result = CSVHealthImporter().prepare(append_row(csv_row(), csv_row()))

    assert result.report.status == "partial"
    assert len(result.observations) == 1
    assert result.report.skipped_records[0].code == "duplicate_record_skipped"


def test_invalid_confidence_is_skipped() -> None:
    result = CSVHealthImporter().prepare(csv_row(confidence="2.0"))

    assert result.report.status == "partial"
    assert result.report.skipped_records


def test_domain_range_violation_is_skipped() -> None:
    result = CSVHealthImporter().prepare(csv_row(value_numeric="-1"))

    assert result.report.status == "partial"
    assert result.observations == []
    assert result.report.skipped_records[0].code == "invalid_record"


def test_non_object_metadata_is_skipped() -> None:
    result = CSVHealthImporter().prepare(csv_row(metadata="[]"))

    assert result.report.status == "partial"
    assert result.report.skipped_records[0].code == "invalid_record"


def test_out_of_order_records_are_sorted_and_reported_as_fixed() -> None:
    first = csv_row(observed_at="2026-07-28T10:00:00+09:00")
    second = csv_row(
        observation_id="33333333-3333-3333-3333-333333333333",
        observed_at="2026-07-28T08:00:00+09:00",
    )
    result = CSVHealthImporter().prepare(append_row(first, second))

    assert result.report.status == "success"
    assert any(item.code == "date_order_sorted" for item in result.report.fixed_issues)
    assert result.observations[0]["observation_id"] != result.observations[1]["observation_id"]
    assert result.observations[0]["observed_at"] < result.observations[1]["observed_at"]


def test_extra_column_is_reported_as_fixed() -> None:
    content = csv_row().decode().replace("metadata", "metadata,extra").replace("{}", "{},x")
    result = CSVHealthImporter().prepare(content.encode())

    assert result.report.status == "success"
    assert any(item.code == "extra_columns_ignored" for item in result.report.fixed_issues)
