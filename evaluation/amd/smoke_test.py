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
from backend.api.app.llm.radeon_local import RadeonLocalProvider


async def run_smoke(prompt: str) -> dict[str, Any]:
    settings = get_settings()
    provider = RadeonLocalProvider(settings)

    health = await provider.health_check()
    if health.get("status") != "ok":
        raise RuntimeError("Radeon runtime is not ready. Start the local ROCm model server first.")

    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "local_inference": {"type": "boolean"},
        },
        "required": ["summary", "local_inference"],
        "additionalProperties": False,
    }
    started = time.perf_counter()
    result = await provider.generate_structured(prompt, schema, seed=0)
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
        description="Run one structured CarePath inference against local Radeon."
    )
    parser.add_argument(
        "--prompt",
        default=(
            "Using only this synthetic scenario, return a concise non-diagnostic summary. "
            "The user slept less this week and reports higher workload stress. "
            "Set local_inference to true."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/amd/results/provider_smoke.json"),
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
