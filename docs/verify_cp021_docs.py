from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"
DIAGRAMS = (
    ROOT / "docs" / "diagrams" / "system-architecture.mmd",
    ROOT / "docs" / "diagrams" / "agent-state-flow.mmd",
    ROOT / "docs" / "diagrams" / "trust-boundaries.mmd",
    ROOT / "docs" / "diagrams" / "deployment-boundary.mmd",
)

QUICKSTART = "docker compose --env-file deployment/.env.compose.example up -d --build --wait"
PUBLIC_URL = "https://carepath-api-8edq.onrender.com"

PUBLIC_DOC_FORBIDDEN_TERMS = (
    "amd",
    "radeon",
    "rocm",
    "tokyo",
    "aws",
    "eth",
)

ARCHITECTURE_TERMS = (
    "React Native / Expo",
    "FastAPI",
    "Safety Triage",
    "Context Builder",
    "Tool Router",
    "Deterministic",
    "Personal Context Retriever",
    "External Evidence Retriever",
    "Planner",
    "Verifier",
    "Response Composer",
    "ModelProvider",
    "PostgreSQL",
)

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise AssertionError(message)


def read(path: Path) -> str:
    if not path.is_file():
        fail(f"required documentation file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def verify_first_screen(readme: str) -> None:
    architecture_heading = readme.find("## Architecture")
    if architecture_heading < 0:
        fail("README is missing the Architecture section")
    preamble = readme[:architecture_heading]
    for marker in (
        "**Problem.**",
        "**System.**",
        "**Reference result.**",
        "**Run locally from a clean clone.**",
    ):
        if marker not in preamble:
            fail(f"README first screen is missing {marker}")
    if PUBLIC_URL not in preamble:
        fail("README first screen is missing the live reviewer URL")
    if QUICKSTART not in preamble:
        fail("README first screen is missing the canonical one-command quickstart")


def verify_limitations(readme: str) -> None:
    required = (
        "## Boundaries and non-goals",
        "research prototype, not a medical service",
        "does not diagnose",
        "mock model provider",
        "synthetic",
    )
    lowered = readme.lower()
    for marker in required:
        if marker.lower() not in lowered:
            fail(f"README limitations/non-goals are missing: {marker}")


def verify_architecture(architecture: str, diagrams: dict[Path, str]) -> None:
    combined = architecture + "\n" + "\n".join(diagrams.values())
    for term in ARCHITECTURE_TERMS:
        if term.lower() not in combined.lower():
            fail(f"architecture contract is missing: {term}")
    if "no direct model-to-database path" not in architecture.lower():
        fail("architecture must explicitly forbid direct model-to-database access")
    if "same origin" not in architecture.lower():
        fail("architecture must describe the integrated same-origin reviewer deployment")


def verify_vendor_neutral_public_docs(texts: dict[Path, str]) -> None:
    for path, text in texts.items():
        lowered = text.lower()
        for term in PUBLIC_DOC_FORBIDDEN_TERMS:
            pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
            if re.search(pattern, lowered):
                fail(
                    f"public core documentation contains vendor/extension-specific term "
                    f"{term!r}: {path.relative_to(ROOT)}"
                )


def verify_local_links(path: Path, text: str) -> None:
    for raw_target in LINK_RE.findall(text):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        parsed = urlparse(target)
        if parsed.scheme or target.startswith(("#", "mailto:")):
            continue
        clean_target = target.split("#", 1)[0].split("?", 1)[0]
        if not clean_target:
            continue
        resolved = (path.parent / clean_target).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise AssertionError(
                f"README/docs link escapes repository: {path.relative_to(ROOT)} -> {target}"
            ) from exc
        if not resolved.exists():
            fail(f"broken local link: {path.relative_to(ROOT)} -> {target}")


def main() -> None:
    readme = read(README)
    architecture = read(ARCHITECTURE)
    diagram_texts = {path: read(path) for path in DIAGRAMS}

    verify_first_screen(readme)
    verify_limitations(readme)
    verify_architecture(architecture, diagram_texts)
    verify_vendor_neutral_public_docs({README: readme, ARCHITECTURE: architecture, **diagram_texts})
    verify_local_links(README, readme)
    verify_local_links(ARCHITECTURE, architecture)

    print("CP-021 documentation contract: OK")
    print(f"quickstart: {QUICKSTART}")
    print(f"reviewer: {PUBLIC_URL}")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"CP-021 documentation contract failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
