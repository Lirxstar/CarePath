"""HTML, Markdown, plain-text, and extracted-PDF text parsers for CP-006."""

from __future__ import annotations

import re
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import ClassVar

from .cleaner import clean_inline, clean_text, is_boilerplate_line
from .models import Section, SourceFormat


class _MainTextHTMLParser(HTMLParser):
    _SKIP_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"nav", "header", "footer", "script", "style", "aside", "form", "noscript"}
    )
    _CONTENT_ROOTS: ClassVar[frozenset[str]] = frozenset({"main", "article"})
    _BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"p", "li", "div", "section", "article", "main", "br"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._content_depth = 0
        self._saw_content_root = False
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._text_parts: list[str] = []
        self.events: list[tuple[str, int | None, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if normalized in self._CONTENT_ROOTS:
            if not self._saw_content_root:
                self._saw_content_root = True
                self.events.clear()
                self._text_parts = []
                self._heading_level = None
                self._heading_parts = []
            self._content_depth += 1
            return
        if self._saw_content_root and self._content_depth == 0:
            return
        if re.fullmatch(r"h[1-6]", normalized):
            self._heading_level = int(normalized[1])
            self._heading_parts = []
        elif normalized in self._BLOCK_TAGS:
            self._flush_text()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in self._SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if normalized in self._CONTENT_ROOTS:
            if self._content_depth:
                self._flush_text()
                self._content_depth -= 1
            return
        if self._saw_content_root and self._content_depth == 0:
            return
        if re.fullmatch(r"h[1-6]", normalized) and self._heading_level is not None:
            heading = clean_inline(" ".join(self._heading_parts))
            if heading:
                self.events.append(("heading", self._heading_level, heading))
            self._heading_level = None
            self._heading_parts = []
        elif normalized in self._BLOCK_TAGS:
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._saw_content_root and self._content_depth == 0:
            return
        if self._heading_level is not None:
            self._heading_parts.append(data)
        else:
            self._text_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_text()

    def _flush_text(self) -> None:
        text = clean_inline(" ".join(self._text_parts))
        if text and not is_boilerplate_line(text):
            self.events.append(("text", None, text))
        self._text_parts = []


def _events_to_sections(events: Iterable[tuple[str, int | None, str]]) -> list[Section]:
    headings: list[str] = []
    paragraphs: list[str] = []
    sections: list[Section] = []

    def flush() -> None:
        if paragraphs:
            sections.append(
                Section(tuple(item for item in headings if item), "\n\n".join(paragraphs))
            )
            paragraphs.clear()

    for kind, level, value in events:
        if kind == "heading":
            flush()
            if level is None:
                raise ValueError("heading event is missing a level")
            headings[:] = headings[: level - 1]
            while len(headings) < level - 1:
                headings.append("")
            headings.append(value)
        else:
            paragraphs.append(value)
    flush()
    return [section for section in sections if section.text.strip()]


def parse_html(text: str) -> list[Section]:
    parser = _MainTextHTMLParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        raise ValueError("HTML parse failed") from exc
    return _events_to_sections(parser.events)


def parse_markdown(text: str) -> list[Section]:
    events: list[tuple[str, int | None, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            value = clean_inline(" ".join(paragraph))
            if value and not is_boilerplate_line(value):
                events.append(("text", None, value))
            paragraph.clear()

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if heading:
            flush()
            events.append(("heading", len(heading.group(1)), clean_inline(heading.group(2))))
        elif not line:
            flush()
        else:
            paragraph.append(re.sub(r"^\s*[-*+]\s+", "", line))
    flush()
    return _events_to_sections(events)


def parse_plain_text(text: str) -> list[Section]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [Section((), paragraph) for paragraph in cleaned.split("\n\n") if paragraph.strip()]


def parse_document(text: str, source_format: SourceFormat) -> list[Section]:
    if source_format is SourceFormat.HTML:
        return parse_html(text)
    if source_format is SourceFormat.MARKDOWN:
        return parse_markdown(text)
    if source_format in {SourceFormat.TEXT, SourceFormat.PDF_TEXT}:
        return parse_plain_text(text)
    raise ValueError(f"unsupported source format: {source_format}")
