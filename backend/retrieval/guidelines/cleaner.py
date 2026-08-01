"""Conservative guideline text cleaning that preserves health semantics."""

from __future__ import annotations

import re

_BOILERPLATE_PREFIXES = (
    "accept cookies",
    "cookie preferences",
    "privacy preferences",
    "skip to main content",
    "back to top",
    "related links",
    "related content",
    "recommended content",
)


def clean_inline(text: str) -> str:
    """Collapse horizontal whitespace without changing words, numbers, or negation."""

    return re.sub(r"[ \t\f\v]+", " ", text).strip()


def is_boilerplate_line(text: str) -> bool:
    normalized = clean_inline(text).lower()
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}:")
        for prefix in _BOILERPLATE_PREFIXES
    )


def clean_text(text: str) -> str:
    """Normalize paragraphs and remove repeated or explicit template noise."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [clean_inline(line) for line in normalized.split("\n")]
    filtered = [line for line in lines if line and not is_boilerplate_line(line)]
    deduplicated: list[str] = []
    for line in filtered:
        if not deduplicated or deduplicated[-1] != line:
            deduplicated.append(line)
    return "\n\n".join(deduplicated).strip()
