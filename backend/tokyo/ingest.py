"""Deterministic adapters and normalisation for CP-201 Tokyo open data."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from collections.abc import Iterable, Mapping
from typing import Any

from backend.tokyo.models import (
    AdapterKind,
    Freshness,
    SourceBuildResult,
    SourceProvenance,
    SourceRegistryEntry,
    TokyoResource,
    TokyoResourceCategory,
)

_NEGATIVE_VALUES = {"", "-", "ー", "0", "無", "無し", "なし", "不可", "非対応", "該当なし", "no"}
_LANGUAGE_HEADERS = {
    "英語": "en",
    "中国語": "zh",
    "中国語(簡体)": "zh-Hans",
    "中国語(繁体)": "zh-Hant",
    "韓国語": "ko",
    "韓国・朝鮮語": "ko",
    "スペイン語": "es",
    "ポルトガル語": "pt",
    "フランス語": "fr",
    "ドイツ語": "de",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def decode_csv_payload(payload: bytes, source_format: str) -> str:
    raw = payload
    if source_format == "zip_csv":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_names = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
            if len(csv_names) != 1:
                raise ValueError(f"ZIP must contain exactly one CSV, found {len(csv_names)}")
            raw = archive.read(csv_names[0])
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV payload is not UTF-8/UTF-8-BOM/CP932")


def read_csv_rows(payload: bytes, source_format: str) -> list[dict[str, str]]:
    text = decode_csv_payload(payload, source_format)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header")
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {
            str(key): str(value or "").strip() for key, value in raw_row.items() if key is not None
        }
        if any(row.values()):
            rows.append(row)
    return rows


def ingest_source(
    source: SourceRegistryEntry,
    payload: bytes,
    resolved_url: str,
) -> tuple[list[TokyoResource], SourceBuildResult]:
    rows = read_csv_rows(payload, source.format.value)
    content_hash = sha256_bytes(payload)
    resources: list[TokyoResource] = []
    skipped = 0
    for row in rows:
        if source.adapter is AdapterKind.MHLW_MEDICAL:
            resource = _adapt_mhlw_medical(source, row, resolved_url, content_hash)
        elif source.adapter is AdapterKind.TOKYO_ODS:
            resource = _adapt_tokyo_ods(source, row, resolved_url, content_hash)
        elif source.adapter is AdapterKind.TOKYO_WELFARE:
            resource = _adapt_tokyo_welfare(source, row, resolved_url, content_hash)
        else:  # pragma: no cover - enum makes this defensive
            raise ValueError(f"unsupported adapter {source.adapter}")
        if resource is None:
            skipped += 1
        else:
            resources.append(resource)
    return resources, SourceBuildResult(
        source_id=source.source_id,
        input_records=len(rows),
        accepted_records=len(resources),
        skipped_records=skipped,
    )


def merge_duplicates(resources: Iterable[TokyoResource]) -> tuple[list[TokyoResource], int]:
    merged: dict[tuple[str, str, str], TokyoResource] = {}
    duplicate_count = 0
    for resource in sorted(resources, key=lambda item: item.resource_id):
        key = (
            resource.category.value,
            _identity_text(resource.name),
            _identity_text(resource.address or f"{resource.latitude},{resource.longitude}"),
        )
        previous = merged.get(key)
        if previous is None:
            merged[key] = resource
            continue
        duplicate_count += 1
        flags = set(previous.data_quality_flags) | set(resource.data_quality_flags)
        updates: dict[str, Any] = {}
        for field_name in ("phone", "website", "opening_hours", "access_notes", "municipality"):
            old_value = getattr(previous, field_name)
            new_value = getattr(resource, field_name)
            if old_value is None and new_value is not None:
                updates[field_name] = new_value
            elif old_value and new_value and old_value != new_value:
                flags.add(f"conflict:{field_name}")
        if previous.latitude is None and resource.latitude is not None:
            updates["latitude"] = resource.latitude
            updates["longitude"] = resource.longitude
        elif (
            previous.latitude is not None
            and resource.latitude is not None
            and (previous.latitude != resource.latitude or previous.longitude != resource.longitude)
        ):
            flags.add("conflict:coordinates")
        updates["languages"] = sorted(set(previous.languages) | set(resource.languages))
        updates["provenance"] = [*previous.provenance, *resource.provenance]
        updates["data_quality_flags"] = sorted(flags)
        updates["freshness"] = _least_fresh(previous.freshness, resource.freshness)
        merged[key] = previous.model_copy(update=updates)
    return sorted(merged.values(), key=lambda item: item.resource_id), duplicate_count


def _adapt_mhlw_medical(
    source: SourceRegistryEntry,
    row: Mapping[str, str],
    resolved_url: str,
    content_hash: str,
) -> TokyoResource | None:
    name = _first(row, ("正式名称", "医療機関名称", "医療機関名", "施設名称", "名称"))
    address = _first(row, ("所在地", "住所", "所在地住所", "医療機関所在地"))
    prefecture = _first(row, ("都道府県", "都道府県名", "所在地都道府県"))
    if prefecture and _identity_text(prefecture) != _identity_text("東京都"):
        return None
    if not prefecture and (not address or "東京都" not in address):
        return None
    if not name or not address:
        return None
    record_id = _first(
        row,
        ("医療機関コード", "医療機関ID", "機関コード", "施設ID", "報告機関ID", "医療機関番号"),
    ) or _row_fingerprint(name, address)
    municipality = _first(row, ("市区町村", "市区町村名", "所在地市区町村"))
    phone = _first(row, ("電話番号", "代表電話番号", "電話"))
    website = _first(row, ("ホームページ", "ホームページURL", "WebサイトURL", "URL"))
    latitude, lat_flag = _coordinate(row, ("緯度", "latitude"), -90, 90)
    longitude, lon_flag = _coordinate(row, ("経度", "longitude"), -180, 180)
    flags = [flag for flag in (lat_flag, lon_flag) if flag]
    if (latitude is None) != (longitude is None):
        latitude = None
        longitude = None
        flags.append("partial_coordinates_discarded")
    languages = _extract_languages(row)
    return _resource(
        source=source,
        resolved_url=resolved_url,
        content_hash=content_hash,
        source_record_id=record_id,
        name=name,
        address=address,
        municipality=municipality,
        latitude=latitude,
        longitude=longitude,
        languages=languages,
        phone=phone,
        website=website,
        opening_hours=None,
        access_notes=None,
        flags=flags,
    )


def _adapt_tokyo_ods(
    source: SourceRegistryEntry,
    row: Mapping[str, str],
    resolved_url: str,
    content_hash: str,
) -> TokyoResource | None:
    name = _first(row, ("名称", "施設名称", "施設名", "名前"))
    address = _first(row, ("住所", "所在地", "所在地住所"))
    if not name or not address:
        return None
    record_id = _first(row, ("ID", "id", "施設ID", "No", "番号")) or _row_fingerprint(name, address)
    latitude, lat_flag = _coordinate(row, ("緯度", "latitude", "lat"), -90, 90)
    longitude, lon_flag = _coordinate(row, ("経度", "longitude", "lon", "lng"), -180, 180)
    flags = [flag for flag in (lat_flag, lon_flag) if flag]
    if (latitude is None) != (longitude is None):
        latitude = None
        longitude = None
        flags.append("partial_coordinates_discarded")
    return _resource(
        source=source,
        resolved_url=resolved_url,
        content_hash=content_hash,
        source_record_id=record_id,
        name=name,
        address=address,
        municipality=_first(row, ("市区町村", "区市町村", "自治体名")),
        latitude=latitude,
        longitude=longitude,
        languages=_extract_languages(row),
        phone=_first(row, ("電話番号", "電話", "TEL")),
        website=_first(row, ("WebサイトURL", "URL", "ホームページ")),
        opening_hours=_first(row, ("利用可能時間", "開設時間", "営業時間", "利用時間")),
        access_notes=_first(row, ("備考", "利用条件", "注意事項")),
        flags=flags,
    )


def _adapt_tokyo_welfare(
    source: SourceRegistryEntry,
    row: Mapping[str, str],
    resolved_url: str,
    content_hash: str,
) -> TokyoResource | None:
    name = _first(row, ("名称", "施設名称", "施設名", "事業所名"))
    address = _first(row, ("所在地", "住所"))
    if not name or not address:
        return None
    record_id = _first(row, ("ID", "施設ID", "番号", "No")) or _row_fingerprint(name, address)
    latitude, lat_flag = _coordinate(row, ("緯度", "latitude"), -90, 90)
    longitude, lon_flag = _coordinate(row, ("経度", "longitude"), -180, 180)
    flags = [flag for flag in (lat_flag, lon_flag) if flag]
    if (latitude is None) != (longitude is None):
        latitude = None
        longitude = None
        flags.append("partial_coordinates_discarded")
    return _resource(
        source=source,
        resolved_url=resolved_url,
        content_hash=content_hash,
        source_record_id=record_id,
        name=name,
        address=address,
        municipality=_first(row, ("区市町村", "市区町村", "自治体名")),
        latitude=latitude,
        longitude=longitude,
        languages=_extract_languages(row),
        phone=_first(row, ("電話番号", "電話", "TEL")),
        website=_first(row, ("URL", "WebサイトURL", "ホームページ")),
        opening_hours=_first(row, ("受付時間", "開所時間", "利用時間")),
        access_notes=_first(row, ("備考", "対象", "利用条件")),
        flags=flags,
    )


def _resource(
    *,
    source: SourceRegistryEntry,
    resolved_url: str,
    content_hash: str,
    source_record_id: str,
    name: str,
    address: str,
    municipality: str | None,
    latitude: float | None,
    longitude: float | None,
    languages: list[str],
    phone: str | None,
    website: str | None,
    opening_hours: str | None,
    access_notes: str | None,
    flags: list[str],
) -> TokyoResource:
    resource_id = _stable_resource_id(source.category, name, address)
    if not languages:
        flags.append("language_support_unknown")
    if latitude is None:
        flags.append("coordinates_unknown")
    if opening_hours is None:
        flags.append("opening_hours_unknown")
    provenance = SourceProvenance(
        source_id=source.source_id,
        source_record_id=source_record_id,
        source_url=resolved_url,
        catalog_url=source.catalog_url,
        publisher=source.publisher,
        licence=source.licence,
        source_as_of=source.source_as_of,
        retrieved_at=source.retrieved_at,
        content_sha256=content_hash,
    )
    return TokyoResource(
        resource_id=resource_id,
        name=name,
        category=source.category,
        address=address,
        municipality=municipality,
        latitude=latitude,
        longitude=longitude,
        languages=languages,
        opening_hours=opening_hours,
        access_notes=access_notes,
        phone=phone,
        website=website,
        freshness=_freshness(source),
        provenance=[provenance],
        data_quality_flags=flags,
    )


def _first(row: Mapping[str, str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_header(key): value.strip() for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(_header(alias), "").strip()
        if value:
            return value
    return None


def _coordinate(
    row: Mapping[str, str], aliases: tuple[str, ...], minimum: float, maximum: float
) -> tuple[float | None, str | None]:
    raw = _first(row, aliases)
    if raw is None:
        return None, None
    try:
        value = float(unicodedata.normalize("NFKC", raw).replace(",", ""))
    except ValueError:
        return None, "invalid_coordinate"
    if value < minimum or value > maximum:
        return None, "invalid_coordinate"
    return value, None


def _extract_languages(row: Mapping[str, str]) -> list[str]:
    found: set[str] = set()
    negative_values = {_identity_text(item) for item in _NEGATIVE_VALUES}
    for raw_header, raw_value in row.items():
        header = unicodedata.normalize("NFKC", raw_header).strip()
        value = unicodedata.normalize("NFKC", raw_value).strip()
        if _identity_text(value) in negative_values:
            continue
        for source_name, code in _LANGUAGE_HEADERS.items():
            if source_name in header and _positive_indicator(value):
                found.add(code)
            if (
                "外国語" in header or "対応言語" in header or header.endswith("言語")
            ) and source_name in value:
                found.add(code)
    return sorted(found)


def _positive_indicator(value: str) -> bool:
    normalized = _identity_text(value)
    negative_values = {_identity_text(item) for item in _NEGATIVE_VALUES}
    if normalized in negative_values:
        return False
    return any(
        token in normalized for token in ("可", "可能", "対応", "あり", "有", "○", "1", "yes")
    ) or bool(normalized)


def _freshness(source: SourceRegistryEntry) -> Freshness:
    if source.source_as_of is None:
        return Freshness.UNKNOWN
    age = (source.retrieved_at - source.source_as_of).days
    if age <= source.max_age_days:
        return Freshness.CURRENT
    if age <= source.max_age_days * 2:
        return Freshness.AGING
    return Freshness.STALE


def _least_fresh(left: Freshness, right: Freshness) -> Freshness:
    order = {Freshness.CURRENT: 0, Freshness.UNKNOWN: 1, Freshness.AGING: 2, Freshness.STALE: 3}
    return max((left, right), key=lambda value: order[value])


def _stable_resource_id(category: TokyoResourceCategory, name: str, address: str) -> str:
    identity = f"{category.value}|{_identity_text(name)}|{_identity_text(address)}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"tokyo-{category.value}-{digest}"


def _row_fingerprint(name: str, address: str) -> str:
    digest = hashlib.sha256(
        f"{_identity_text(name)}|{_identity_text(address)}".encode()
    ).hexdigest()
    return f"row-{digest[:20]}"


def _identity_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s\-\u2010\u2011\u2012\u2013\u2014\u2015・,。()]", "", value)


def _header(value: str) -> str:
    return _identity_text(value).replace("_", "")
