#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.api.app.config import get_settings
from backend.api.app.llm.radeon_local import RadeonLocalProvider

PROMPT = (
    "Using only this synthetic scenario, return a concise non-diagnostic summary "
    "and one realistic low-effort action. The user slept less this week, reports "
    "higher workload stress, and completed only one of four previous actions."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "action": {"type": "string"},
    },
    "required": ["summary", "action"],
    "additionalProperties": False,
}


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


async def run_benchmark(warmups: int, repetitions: int) -> dict[str, Any]:
    provider = RadeonLocalProvider(get_settings())
    health = await provider.health_check()
    if health.get("status") != "ok":
        raise RuntimeError("Radeon runtime is not ready")

    for _ in range(warmups):
        await provider.generate_structured(PROMPT, SCHEMA, seed=0)

    rows = []
    for index in range(repetitions):
        started = time.perf_counter()
        try:
            result = await provider.generate_structured(PROMPT, SCHEMA, seed=0)
        except Exception as exc:
            rows.append(
                {
                    "iteration": index,
                    "success": False,
                    "elapsed_seconds": time.perf_counter() - started,
                    "error_class": type(exc).__name__,
                }
            )
        else:
            rows.append(
                {
                    "iteration": index,
                    "success": True,
                    "elapsed_seconds": time.perf_counter() - started,
                    "structured_output_valid": isinstance(result, dict),
                }
            )

    successful = [float(row["elapsed_seconds"]) for row in rows if row["success"] is True]
    return {
        "schema_version": "1.0",
        "captured_at": datetime.now(UTC).isoformat(),
        "provider_health": health,
        "warmups": warmups,
        "repetitions": repetitions,
        "raw_requests": rows,
        "summary": {
            "success_rate": len(successful) / repetitions,
            "latency_p50_seconds": percentile(successful, 0.50) if successful else None,
            "latency_p95_seconds": percentile(successful, 0.95) if successful else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the initial local Radeon provider latency benchmark."
    )
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/amd/results/provider_benchmark.json"),
    )
    args = parser.parse_args()
    if args.warmups < 0 or args.repetitions < 1:
        parser.error("warmups must be >= 0 and repetitions must be >= 1")

    payload = asyncio.run(run_benchmark(args.warmups, args.repetitions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
