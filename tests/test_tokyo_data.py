from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from backend.tokyo.ingest import ingest_source, merge_duplicates
from backend.tokyo.models import (
    AdapterKind,
    SourceFormat,
    SourceRegistry,
    SourceRegistryEntry,
    TokyoResourceCategory,
)
from backend.tokyo.pipeline import build_resources, write_artifacts
from backend.tokyo.registry import resolve_download_url


def _source(
    *,
    source_id: str = "test-source",
    adapter: AdapterKind = AdapterKind.TOKYO_ODS,
    category: TokyoResourceCategory = TokyoResourceCategory.COOLING_SHELTER,
    source_format: SourceFormat = SourceFormat.CSV,
) -> SourceRegistryEntry:
    return SourceRegistryEntry(
        source_id=source_id,
        title="Test source",
        publisher="Public authority",
        catalog_url="https://example.gov/catalog",
        download_url="https://example.gov/data.csv",
        format=source_format,
        adapter=adapter,
        category=category,
        licence="CC BY",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        source_as_of=date(2026, 8, 1),
        retrieved_at=date(2026, 8, 12),
        max_age_days=365,
    )


def _zip_csv(text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("data.csv", text.encode("utf-8-sig"))
    return output.getvalue()


def test_registry_forbids_ambiguous_locator_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        SourceRegistryEntry.model_validate(
            {
                **_source(source_id="bad").model_dump(),
                "ckan_dataset_id": "d",
                "ckan_resource_name": "r",
            }
        )
    source = _source()
    with pytest.raises(ValidationError):
        SourceRegistry(schema_version="cp201-v1", sources=[source, source])


def test_mhlw_adapter_filters_to_tokyo_and_keeps_language_evidence() -> None:
    source = _source(
        source_id="mhlw-test",
        adapter=AdapterKind.MHLW_MEDICAL,
        category=TokyoResourceCategory.HEALTHCARE,
        source_format=SourceFormat.ZIP_CSV,
    )
    csv_text = (
        "医療機関ID,正式名称,都道府県,所在地,電話番号,英語対応,中国語対応\n"
        "t1,Tokyo Clinic,東京都,東京都江東区1-1,03-0000-0000,対応可能,不可\n"
        "o1,Osaka Clinic,大阪府,大阪府大阪市1-1,06-0000-0000,対応可能,対応可能\n"
    )
    resources, result = ingest_source(source, _zip_csv(csv_text), source.download_url or "")
    assert result.input_records == 2
    assert result.accepted_records == 1
    assert result.skipped_records == 1
    resource = resources[0]
    assert resource.name == "Tokyo Clinic"
    assert resource.languages == ["en"]
    assert "coordinates_unknown" in resource.data_quality_flags
    assert resource.provenance[0].source_record_id == "t1"
    assert len(resource.provenance[0].content_sha256) == 64


def test_unknown_language_and_opening_hours_remain_explicit() -> None:
    source = _source()
    payload = "名称,住所,緯度,経度\nShelter A,東京都江東区2-2,35.67,139.81\n".encode()
    resources, _ = ingest_source(source, payload, source.download_url or "")
    resource = resources[0]
    assert resource.languages == []
    assert resource.opening_hours is None
    assert "language_support_unknown" in resource.data_quality_flags
    assert "opening_hours_unknown" in resource.data_quality_flags


def test_invalid_or_partial_coordinates_are_not_presented_as_valid() -> None:
    source = _source()
    payload = (
        "名称,住所,緯度,経度\n"
        "Bad coordinate,東京都江東区3-3,not-a-number,139.8\n"
        "Partial coordinate,東京都江東区4-4,35.6,\n"
    ).encode()
    resources, _ = ingest_source(source, payload, source.download_url or "")
    assert len(resources) == 2
    for resource in resources:
        assert resource.latitude is None
        assert resource.longitude is None
        assert "partial_coordinates_discarded" in resource.data_quality_flags


def test_duplicates_merge_provenance_and_flag_conflicts() -> None:
    source_a = _source(source_id="source-a")
    source_b = _source(source_id="source-b")
    payload_a = "名称,住所,電話番号\nSame Place,東京都江東区5-5,03-1111-1111\n".encode()
    payload_b = "名称,住所,電話番号\nSame Place,東京都江東区5-5,03-2222-2222\n".encode()
    first, _ = ingest_source(source_a, payload_a, source_a.download_url or "")
    second, _ = ingest_source(source_b, payload_b, source_b.download_url or "")
    merged, count = merge_duplicates([*first, *second])
    assert count == 1
    assert len(merged) == 1
    assert len(merged[0].provenance) == 2
    assert "conflict:phone" in merged[0].data_quality_flags


def test_ckan_resolution_requires_exact_named_csv() -> None:
    source = SourceRegistryEntry(
        source_id="ckan-test",
        title="Test",
        publisher="Tokyo",
        catalog_url="https://catalog.data.metro.tokyo.lg.jp/dataset/x",
        ckan_dataset_id="x",
        ckan_resource_name="子供家庭支援センター",
        format=SourceFormat.CSV,
        adapter=AdapterKind.TOKYO_WELFARE,
        category=TokyoResourceCategory.FAMILY_SUPPORT,
        licence="CC BY",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        source_as_of=date(2025, 10, 1),
        retrieved_at=date(2026, 8, 12),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["id"] == "x"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "resources": [
                        {
                            "name": "子供家庭支援センターCSV",
                            "format": "CSV",
                            "url": "https://example.metro.tokyo.lg.jp/family.csv",
                        }
                    ]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert resolve_download_url(source, client).endswith("family.csv")


def test_build_and_serialisation_are_deterministic(tmp_path) -> None:
    source = _source()
    registry = SourceRegistry(schema_version="cp201-v1", sources=[source])
    payload = ("名称,住所\nB Shelter,東京都江東区2-2\nA Shelter,東京都江東区1-1\n").encode()
    resources, report = build_resources(
        registry,
        {source.source_id: payload},
        {source.source_id: source.download_url or ""},
    )
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first_report = tmp_path / "first-report.json"
    second_report = tmp_path / "second-report.json"
    write_artifacts(resources, report, output_path=first, report_path=first_report)
    write_artifacts(resources, report, output_path=second, report_path=second_report)
    assert first.read_bytes() == second.read_bytes()
    assert first_report.read_bytes() == second_report.read_bytes()
    parsed = [json.loads(line) for line in first.read_text().splitlines()]
    assert [item["resource_id"] for item in parsed] == sorted(
        item["resource_id"] for item in parsed
    )
