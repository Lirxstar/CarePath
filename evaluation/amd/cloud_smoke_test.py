#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.api.app.config import get_settings
from backend.api.app.llm.radeon_cloud import RadeonCloudProvider


async def run_smoke(prompt: str) -> dict[str, Any]:
    settings = get_settings()
    provider = RadeonCloudProvider(settings)
    health = await provider.health_check()

    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "action": {"type": "string"},
            "diagnostic_claim": {"type": "boolean"},
        },
        "required": ["summary", "action", "diagnostic_claim"],
        "additionalProperties": False,
    }
    started = time.perf_counter()
    result = await provider.generate_structured(prompt, schema)
    elapsed = time.perf_counter() - started

    return {
        "schema_version": "1.0",
        "captured_at": datetime.now(UTC).isoformat(),
        "provider_health": health,
        "elapsed_seconds": elapsed,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one synthetic structured request against AMD Radeon Cloud."
    )
    parser.add_argument(
        "--prompt",
        default=(
            "Using only this synthetic scenario, provide a concise non-diagnostic "
            "summary and one low-effort action. The user slept less this week, "
            "reports higher workload stress, and completed one of four prior actions. "
            "Set diagnostic_claim to false."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/amd/results/cloud_provider_smoke.json"),
    )
    args = parser.parse_args()

    payload = asyncio.run(run_smoke(args.prompt))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
