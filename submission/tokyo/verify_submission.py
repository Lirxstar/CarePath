from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBMISSION = ROOT / "submission" / "tokyo"

REQUIRED = [
    "README.md",
    "form_content.md",
    "open_data.md",
    "pitch_script.md",
    "demo_script.md",
    "claims_audit.md",
    "links.md",
    "engineering_results.json",
]

EXPECTED_SOURCE_IDS = {
    "mhlw-medical-hospitals-20260601",
    "mhlw-medical-clinics-20260601",
    "koto-cooling-shelters",
    "tokyo-child-family-support-centres-202510",
    "tokyo-mental-health-welfare-centres-202510",
}

FORBIDDEN_CLAIMS = [
    r"clinically validated",
    r"clinical effectiveness (?:is|was) proven",
    r"guarantees? (?:a )?facility is open",
    r"public deployment uses a live generative-ai model",
]


def main() -> None:
    for name in REQUIRED:
        path = SUBMISSION / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise SystemExit(f"missing or empty CP-209 submission file: {path}")

    public_origin = (ROOT / "deployment" / "public_backend_url.txt").read_text(
        encoding="utf-8"
    ).strip()
    if not public_origin.startswith("https://"):
        raise SystemExit("public demo origin must use HTTPS")

    sources = json.loads(
        (ROOT / "data" / "tokyo" / "sources.json").read_text(encoding="utf-8")
    )
    source_ids = {item["source_id"] for item in sources["sources"]}
    if source_ids != EXPECTED_SOURCE_IDS:
        raise SystemExit(f"submission source list drifted: {sorted(source_ids)}")

    open_data = (SUBMISSION / "open_data.md").read_text(encoding="utf-8")
    for source_id in EXPECTED_SOURCE_IDS:
        if source_id not in open_data:
            raise SystemExit(f"open_data.md is missing source {source_id}")

    results = json.loads(
        (SUBMISSION / "engineering_results.json").read_text(encoding="utf-8")
    )
    if results.get("evaluation_kind") != "software_engineering_acceptance":
        raise SystemExit("engineering result kind must remain software_engineering_acceptance")
    if results.get("clinical_effectiveness_claimed") is not False:
        raise SystemExit("CP-209 must not claim clinical effectiveness")
    if (results.get("cases_passed"), results.get("cases_total")) != (24, 24):
        raise SystemExit("CP-207 case count drifted")
    if results.get("metrics", {}).get("unsupported_factual_resource_claims") != 0:
        raise SystemExit("unsupported factual resource claim metric drifted")

    public_claim_files = [
        "README.md",
        "form_content.md",
        "pitch_script.md",
        "demo_script.md",
        "links.md",
    ]
    combined = "\n".join(
        (SUBMISSION / name).read_text(encoding="utf-8") for name in public_claim_files
    ).lower()
    for pattern in FORBIDDEN_CLAIMS:
        if re.search(pattern, combined):
            raise SystemExit(f"forbidden CP-209 claim matched: {pattern}")

    cp208 = (ROOT / "docs" / "cp208_public_tokyo_demo.md").read_text(encoding="utf-8")
    if "Render uses `/health/tokyo` as its service health check" in cp208:
        raise SystemExit("stale CP-208 Render health-check claim remains")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    if "healthCheckPath: /health/live" not in render:
        raise SystemExit("Render platform probe contract drifted")

    form = (SUBMISSION / "form_content.md").read_text(encoding="utf-8")
    if f"{public_origin}/tokyo" not in form:
        raise SystemExit("form draft does not contain the canonical public Tokyo demo URL")

    print("CP-209 submission contract: PASS")


if __name__ == "__main__":
    main()
