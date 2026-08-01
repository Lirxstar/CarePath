from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.retrieval.guidelines.audit import audit_chunks
from backend.retrieval.guidelines.cleaner import clean_text
from backend.retrieval.guidelines.ingest import (
    build_ingestion_report,
    build_manifest,
    fetch_error_result,
    ingest_batch,
    ingest_document,
    load_registry,
    validate_registry,
    write_corpus,
)
from backend.retrieval.guidelines.models import (
    ChunkConfig,
    FailureCode,
    GuidelineTopic,
    RedistributionPolicy,
    SourceFormat,
    SourceRegistryEntry,
    normalize_url,
    stable_source_id,
)
from backend.retrieval.guidelines.parsers import (
    parse_html,
    parse_markdown,
    parse_plain_text,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "guidelines" / "sources.yaml"


def make_source(
    *,
    url: str = "https://example.gov/guide",
    topics: list[GuidelineTopic] | None = None,
    policy: RedistributionPolicy = RedistributionPolicy.FULL_TEXT_ALLOWED,
) -> SourceRegistryEntry:
    return SourceRegistryEntry(
        source_id=stable_source_id(url),
        title="Example guidance",
        organisation="Example Public Health Agency",
        canonical_url=url,
        published_at=date(2025, 1, 1),
        updated_at=date(2026, 1, 1),
        retrieved_at=date(2026, 7, 29),
        topics=topics or [GuidelineTopic.PHYSICAL_ACTIVITY],
        language="en",
        document_type="public_health_guidance",
        authority_type="government",
        license="public domain",
        redistribution_policy=policy,
        full_text_storage_allowed=policy is RedistributionPolicy.FULL_TEXT_ALLOWED,
        notes="Fixture metadata for deterministic CP-006 tests.",
    )


def test_registry_meets_cp006_source_acceptance() -> None:
    sources = load_registry(REGISTRY)
    assert 15 <= len(sources) <= 25
    assert len({source.source_id for source in sources}) == len(sources)
    assert len({normalize_url(source.canonical_url) for source in sources}) == len(sources)
    assert {topic for source in sources for topic in source.topics} == set(GuidelineTopic)
    assert all(source.title and source.organisation and source.canonical_url for source in sources)
    assert all(source.license and source.notes for source in sources)
    assert all(source.retrieved_at == date(2026, 7, 29) for source in sources)


def test_source_id_is_stable_after_url_normalization() -> None:
    first = "HTTPS://Example.GOV/guide/?utm_source=test&b=2&a=1"
    second = "https://example.gov/guide?a=1&b=2"
    assert normalize_url(first) == normalize_url(second)
    assert stable_source_id(first) == stable_source_id(second)


def test_invalid_source_metadata_fails_explicitly() -> None:
    source = make_source().model_dump()
    source["source_id"] = "random-id"
    with pytest.raises(ValidationError, match="deterministic"):
        SourceRegistryEntry.model_validate(source)


def test_storage_policy_cannot_claim_full_text_for_derived_chunks() -> None:
    source = make_source(policy=RedistributionPolicy.DERIVED_CHUNKS_ALLOWED).model_dump()
    source["full_text_storage_allowed"] = True
    with pytest.raises(ValidationError, match="full_text_storage_allowed"):
        SourceRegistryEntry.model_validate(source)


def test_html_parser_removes_template_noise_and_preserves_negation() -> None:
    html = """
    <header>Site header</header><nav>Home Sleep About</nav>
    <main><h1>Sleep guidance</h1>
    <p>Adults should keep a regular schedule.</p>
    <h2>Safety</h2><p>Do not ignore persistent sleep problems.</p></main>
    <footer>Footer links</footer>
    """
    sections = parse_html(html)
    text = " ".join(section.text for section in sections)
    assert "regular schedule" in text
    assert "Do not ignore" in text
    assert "Site header" not in text
    assert "Home Sleep About" not in text
    assert "Footer links" not in text
    assert sections[-1].path == ("Sleep guidance", "Safety")


def test_markdown_parser_preserves_heading_hierarchy_and_lists() -> None:
    sections = parse_markdown(
        "# Activity\n\nMove regularly.\n\n## Plan\n\n- Start small.\n- Track progress."
    )
    assert sections[0].path == ("Activity",)
    assert sections[1].path == ("Activity", "Plan")
    assert "Start small." in sections[1].text
    assert "Track progress." in sections[1].text


def test_plain_and_pdf_text_share_conservative_cleaning() -> None:
    text = "Cookie preferences\n\nKeep 150 minutes as written.\n\nDo not remove the qualifier."
    expected = ["Keep 150 minutes as written.", "Do not remove the qualifier."]
    assert [section.text for section in parse_plain_text(text)] == expected
    result = ingest_document(make_source(), text, SourceFormat.PDF_TEXT)
    assert result.failure is None
    assert "Do not remove" in " ".join(chunk.content for chunk in result.chunks)


def test_cleaner_removes_only_conservative_noise_and_adjacent_duplicates() -> None:
    cleaned = clean_text(
        "Skip to main content\nRecommendation 7 hours.\nRecommendation 7 hours.\n"
        "Do not shorten this statement."
    )
    assert cleaned.count("Recommendation 7 hours.") == 1
    assert "Skip to main content" not in cleaned
    assert "Do not shorten" in cleaned


def test_empty_document_returns_structured_failure() -> None:
    result = ingest_document(make_source(), "  \n ", SourceFormat.TEXT)
    assert result.failure is not None
    assert result.failure.code is FailureCode.EMPTY_CONTENT
    assert result.chunks == ()


def test_unsupported_format_returns_structured_failure() -> None:
    result = ingest_document(make_source(), "content", "docx")
    assert result.failure is not None
    assert result.failure.code is FailureCode.UNSUPPORTED_FORMAT


def test_metadata_only_source_never_emits_content() -> None:
    source = make_source(policy=RedistributionPolicy.METADATA_ONLY)
    result = ingest_document(source, "Copyrighted full text must not be stored.", SourceFormat.TEXT)
    assert result.failure is not None
    assert result.failure.code is FailureCode.LICENSE_RESTRICTED
    assert result.source_content_hash is None
    assert result.chunks == ()


def test_reproducibility_preserves_ids_order_hashes_content_and_metadata() -> None:
    source = make_source(topics=[GuidelineTopic.SLEEP])
    markdown = (
        "# Sleep\n\nKeep a regular sleep schedule. Do not remove safety qualifiers.\n\n"
        "## Routine\n\nReduce avoidable disruption and review persistent problems "
        "with a professional."
    )
    config = ChunkConfig(chunk_size=90, chunk_overlap=20, minimum_chunk_size=30)
    first = ingest_document(source, markdown, SourceFormat.MARKDOWN, config=config)
    second = ingest_document(source, markdown, SourceFormat.MARKDOWN, config=config)
    assert first.failure is None and second.failure is None
    assert first.source_content_hash == second.source_content_hash
    assert [chunk.model_dump(mode="json") for chunk in first.chunks] == [
        chunk.model_dump(mode="json") for chunk in second.chunks
    ]
    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]


def test_chunk_boundaries_and_provenance_are_section_aware() -> None:
    source = make_source(topics=[GuidelineTopic.BEHAVIOUR_CHANGE])
    text = (
        "# Goals\n\nSet a specific goal and review progress each week. "
        "Do not increase the target when the current action is not feasible.\n\n"
        "## Monitoring\n\nTrack the action consistently and use the result to revise the next step."
    )
    config = ChunkConfig(chunk_size=100, chunk_overlap=20, minimum_chunk_size=30)
    result = ingest_document(source, text, SourceFormat.MARKDOWN, config=config)
    assert result.failure is None
    assert all(len(chunk.content) <= config.chunk_size for chunk in result.chunks)
    assert all(chunk.title == source.title for chunk in result.chunks)
    assert all(
        chunk.canonical_url == normalize_url(source.canonical_url) for chunk in result.chunks
    )
    assert [chunk.chunk_index for chunk in result.chunks] == list(range(len(result.chunks)))
    assert any(chunk.section_title == "Monitoring" for chunk in result.chunks)
    assert "Do not increase" in " ".join(chunk.content for chunk in result.chunks)


def test_duplicate_source_and_duplicate_content_are_reported() -> None:
    first = make_source(url="https://example.gov/first")
    second = make_source(url="https://example.gov/second")
    content = "A sufficiently long evidence paragraph for duplicate detection and chunk creation."
    same_source_results = ingest_batch(
        [(first, content, SourceFormat.TEXT), (first, content, SourceFormat.TEXT)]
    )
    assert same_source_results[1].failure is not None
    assert same_source_results[1].failure.code is FailureCode.DUPLICATE

    same_content_results = ingest_batch(
        [(first, content, SourceFormat.TEXT), (second, content, SourceFormat.TEXT)]
    )
    assert same_content_results[1].failure is not None
    assert same_content_results[1].failure.code is FailureCode.DUPLICATE
    assert same_content_results[1].duplicate_of == first.source_id


def test_manifest_and_report_are_deterministic_and_include_policy_summary() -> None:
    allowed = make_source(url="https://example.gov/allowed")
    restricted = make_source(
        url="https://example.org/restricted",
        policy=RedistributionPolicy.METADATA_ONLY,
    )
    results = ingest_batch(
        [
            (allowed, "One complete guidance paragraph for the manifest.", SourceFormat.TEXT),
            (restricted, "restricted content", SourceFormat.TEXT),
        ]
    )
    first_manifest = build_manifest(results)
    second_manifest = build_manifest(results)
    assert first_manifest == second_manifest
    assert first_manifest["source_count"] == 2
    assert first_manifest["chunk_count"] == 1
    assert first_manifest["license_policy_summary"] == {
        "full_text_allowed": 1,
        "metadata_only": 1,
    }
    report = build_ingestion_report(results)
    statuses = [item["status"] for item in report["sources"]]  # type: ignore[index]
    assert statuses == ["ok", "restricted"]


def test_write_corpus_writes_only_permitted_derived_chunks(tmp_path: Path) -> None:
    allowed = make_source(url="https://example.gov/allowed-output")
    restricted = make_source(
        url="https://example.org/restricted-output",
        policy=RedistributionPolicy.METADATA_ONLY,
    )
    results = ingest_batch(
        [
            (allowed, "Allowed evidence content for deterministic storage.", SourceFormat.TEXT),
            (restricted, "SECRET_RESTRICTED_TEXT", SourceFormat.TEXT),
        ]
    )
    write_corpus(tmp_path, results)
    chunks = (tmp_path / "chunks.jsonl").read_text(encoding="utf-8")
    assert "Allowed evidence content" in chunks
    assert "SECRET_RESTRICTED_TEXT" not in chunks
    assert (tmp_path / "corpus_manifest.json").is_file()
    assert (tmp_path / "ingestion_report.json").is_file()


def test_fetch_error_is_structured() -> None:
    result = fetch_error_result(make_source(), "network unavailable")
    assert result.failure is not None
    assert result.failure.code is FailureCode.FETCH_ERROR
    assert result.failure.reason == "network unavailable"


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (ChunkConfig(chunk_size=0), "positive"),
        (ChunkConfig(chunk_size=10, chunk_overlap=10), "overlap"),
        (
            ChunkConfig(chunk_size=10, chunk_overlap=0, minimum_chunk_size=11),
            "minimum_chunk_size",
        ),
    ],
)
def test_invalid_chunk_config_is_rejected(config: ChunkConfig, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        config.validate()


def test_registry_validation_rejects_missing_topic_coverage() -> None:
    sources = [make_source(url=f"https://example.gov/{index}") for index in range(15)]
    with pytest.raises(ValueError, match="missing required topics"):
        validate_registry(sources)


def test_load_registry_rejects_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text("not json-compatible yaml", encoding="utf-8")
    with pytest.raises(ValueError, match="unable to load"):
        load_registry(path)


def test_audit_samples_at_least_30_chunks_across_sources_and_topics() -> None:
    topics = list(GuidelineTopic)
    all_chunks = []
    config = ChunkConfig(chunk_size=90, chunk_overlap=10, minimum_chunk_size=25)
    for index, topic in enumerate(topics):
        source = make_source(url=f"https://example.gov/audit/{index}", topics=[topic])
        sentences = [
            f"Section {number} provides a complete recommendation that should remain intact."
            for number in range(10)
        ]
        text = "# Guidance\n\n" + "\n\n".join(sentences)
        result = ingest_document(source, text, SourceFormat.MARKDOWN, config=config)
        assert result.failure is None
        all_chunks.extend(result.chunks)

    report = audit_chunks(all_chunks, sample_size=30)
    assert report["sample_size"] == 30
    assert report["distinct_sources"] == len(topics)
    assert report["distinct_topics"] == sorted(topic.value for topic in topics)
    assert report["all_content_present"] is True
    assert report["navigation_noise_count"] == 0
    assert report["duplicate_chunk_id_count"] == 0


def test_audit_rejects_too_small_sample() -> None:
    with pytest.raises(ValueError, match="at least 30"):
        audit_chunks([], sample_size=29)
