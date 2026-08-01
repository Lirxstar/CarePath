from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from .models import ImportIssue, ImportReport, PreparedImport
from .validators import REQUIRED_OBSERVATION_FIELDS, content_hash, validate_observation

_UNIT_ALIASES = {
    "h": "hours",
    "hour": "hours",
    "hr": "hours",
    "min": "minutes",
    "minute": "minutes",
    "beats/min": "bpm",
    "beats/minute": "bpm",
    "/min": "bpm",
    "score": "score_1_10",
    "count": "steps",
    "{steps}": "steps",
}
_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no"}


class CSVHealthImporter:
    """Validate the frozen CP-003 observation CSV before persistence."""

    def prepare(self, data: bytes) -> PreparedImport:
        source_hash = content_hash(data)
        imported_at = datetime.now(UTC)
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return self._failed(source_hash, imported_at, "invalid_encoding", str(exc))

        try:
            reader = csv.DictReader(io.StringIO(text, newline=""))
            fields = set(reader.fieldnames or [])
            rows = list(reader)
        except csv.Error as exc:
            return self._failed(source_hash, imported_at, "malformed_csv", str(exc))

        missing = REQUIRED_OBSERVATION_FIELDS - fields
        if missing:
            return PreparedImport(
                report=ImportReport(
                    status="failed",
                    source_format="csv",
                    source_hash=source_hash,
                    imported_at=imported_at,
                    received_records=len(rows),
                    inserted_records=0,
                    blocking_errors=[
                        ImportIssue(
                            code="missing_columns",
                            message=f"Missing required columns: {', '.join(sorted(missing))}",
                        )
                    ],
                )
            )

        fixed: list[ImportIssue] = []
        skipped: list[ImportIssue] = []
        blocking: list[ImportIssue] = []
        extras = sorted(fields - REQUIRED_OBSERVATION_FIELDS)
        if extras:
            fixed.append(
                ImportIssue(
                    code="extra_columns_ignored",
                    message=f"Ignored extra columns: {', '.join(extras)}",
                )
            )

        observations: list[dict[str, object]] = []
        seen: dict[str, dict[str, object]] = {}
        order_keys: list[tuple[str, str, datetime]] = []
        for index, row in enumerate(rows):
            try:
                payload, repairs = self._parse_row(row)
                for repair in repairs:
                    fixed.append(
                        ImportIssue(
                            code=repair[0],
                            message=repair[1],
                            record_index=index,
                        )
                    )
                validated = validate_observation(payload)
            except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                skipped.append(
                    ImportIssue(
                        code="invalid_record",
                        message=str(exc),
                        record_index=index,
                    )
                )
                continue

            observation_id = str(validated["observation_id"])
            previous = seen.get(observation_id)
            if previous is not None:
                if previous == validated:
                    skipped.append(
                        ImportIssue(
                            code="duplicate_record_skipped",
                            message="Identical duplicate observation was skipped",
                            record_index=index,
                            original_value=observation_id,
                        )
                    )
                    continue
                blocking.append(
                    ImportIssue(
                        code="conflicting_duplicate",
                        message="Observation ID appears more than once with different content",
                        record_index=index,
                        original_value=observation_id,
                    )
                )
                continue

            seen[observation_id] = validated
            observations.append(validated)
            order_keys.append(
                (
                    str(validated["user_id"]),
                    str(validated["metric_type"]),
                    validated["observed_at"],  # type: ignore[arg-type]
                )
            )

        if blocking:
            return PreparedImport(
                report=ImportReport(
                    status="failed",
                    source_format="csv",
                    source_hash=source_hash,
                    imported_at=imported_at,
                    received_records=len(rows),
                    inserted_records=0,
                    fixed_issues=fixed,
                    skipped_records=skipped,
                    blocking_errors=blocking,
                )
            )

        if order_keys != sorted(order_keys):
            observations.sort(
                key=lambda item: (
                    str(item["user_id"]),
                    str(item["metric_type"]),
                    item["observed_at"],
                )
            )
            fixed.append(
                ImportIssue(
                    code="date_order_sorted",
                    message="Observations were reordered by user, metric, and timestamp",
                )
            )

        return PreparedImport(
            report=ImportReport(
                status="partial" if skipped else "success",
                source_format="csv",
                source_hash=source_hash,
                imported_at=imported_at,
                received_records=len(rows),
                inserted_records=0,
                fixed_issues=fixed,
                skipped_records=skipped,
            ),
            observations=observations,
        )

    @staticmethod
    def _parse_row(row: dict[str, str | None]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
        repairs: list[tuple[str, str]] = []
        payload: dict[str, Any] = {key: row.get(key) for key in REQUIRED_OBSERVATION_FIELDS}
        raw_numeric = row.get("value_numeric") or ""
        raw_boolean = (row.get("value_boolean") or "").strip().lower()
        raw_confidence = row.get("confidence") or ""
        raw_unit = (row.get("unit") or "").strip()
        raw_metadata = row.get("metadata") or ""

        payload["value_numeric"] = float(raw_numeric) if raw_numeric else None
        if raw_boolean in _TRUE_VALUES:
            payload["value_boolean"] = True
        elif raw_boolean in _FALSE_VALUES:
            payload["value_boolean"] = False
        elif raw_boolean:
            raise ValueError(f"invalid boolean value: {raw_boolean}")
        else:
            payload["value_boolean"] = None
        payload["confidence"] = float(raw_confidence) if raw_confidence else None
        if raw_unit.lower() in _UNIT_ALIASES:
            normalized = _UNIT_ALIASES[raw_unit.lower()]
            repairs.append(("unit_normalized", f"Normalized unit {raw_unit!r} to {normalized!r}"))
            raw_unit = normalized
        payload["unit"] = raw_unit or None
        if raw_metadata:
            metadata = json.loads(raw_metadata)
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
            payload["metadata"] = metadata
        else:
            payload["metadata"] = None

        original_source = row.get("source_type")
        payload["source_type"] = "csv"
        metadata_payload = payload["metadata"] or {}
        if not isinstance(metadata_payload, dict):
            raise ValueError("metadata must be a JSON object")
        if original_source and original_source != "csv":
            metadata_payload["original_source_type"] = original_source
        payload["metadata"] = metadata_payload or None
        return payload, repairs

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
                source_format="csv",
                source_hash=source_hash,
                imported_at=imported_at,
                received_records=0,
                inserted_records=0,
                blocking_errors=[ImportIssue(code=code, message=message)],
            )
        )
