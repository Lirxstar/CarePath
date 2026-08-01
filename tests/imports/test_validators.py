from datetime import UTC, datetime

import pytest

from backend.imports.validators import content_hash, parse_timestamp


def test_content_hash_is_stable_sha256() -> None:
    expected = "177f13da1f050667e1c7e5041cfdd51bed36b26e0cfb89f1a7ef5feae9e82869"
    assert content_hash(b"carepath") == expected


def test_parse_timestamp_normalizes_timezone_to_utc() -> None:
    parsed = parse_timestamp("2026-07-28T09:30:00+09:00")

    assert parsed == datetime(2026, 7, 28, 0, 30, tzinfo=UTC)


def test_parse_timestamp_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        parse_timestamp("2026-07-28T09:30:00")
