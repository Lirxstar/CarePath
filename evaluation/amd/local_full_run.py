#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.evaluation.scenarios import load_scenario_set
from evaluation.amd.capture_environment import build_manifest
from evaluation.amd.privacy_egress_check import run_check
from evaluation.amd.real_provider_suite import _resolve_provider, run_suite

VRAM_PATTERN = re.compile(r"VRAM Total Used Memory \(B\)\s*:\s*(\d+)")
GPU_USE_PATTERN = re.compile(r"GPU use \(%\)\s*:\s*(\d+(?:\.\d+)?)")


def _resource_sample() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["rocm-smi", "--showuse", "--showmeminfo", "vram"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "captured_at": datetime.now(UTC).isoformat(),
            "available": False,
            "error_class": type(exc).__name__,
        }
    sample: dict[str, Any] = {
        "captured_at": datetime.now(UTC).isoformat(),
        "available": completed.returncode == 0,
        "returncode": completed.returncode,
    }
    vram = VRAM_PATTERN.search(completed.stdout)
    gpu_use = GPU_USE_PATTERN.search(completed.stdout)
    if vram:
        sample["vram_used_bytes"] = int(vram.group(1))
    if gpu_use:
        sample["gpu_use_percent"] = float(gpu_use.group(1))
    return sample


async def _sampler(stop: asyncio.Event, samples: list[dict[str, Any]]) -> None:
    while not stop.is_set():
        samples.append(await asyncio.to_thread(_resource_sample))
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.5)
        except TimeoutError:
            continue


def _summarize_resources(samples: list[dict[str, Any]]) -> dict[str, Any]:
    available = [sample for sample in samples if sample.get("available") is True]
    vram = [
        int(sample["vram_used_bytes"])
        for sample in available
        if isinstance(sample.get("vram_used_bytes"), int)
    ]
    gpu_use = [
        float(sample["gpu_use_percent"])
        for sample in available
        if isinstance(sample.get("gpu_use_percent"), (int, float))
    ]
    return {
        "sampling_command": ["rocm-smi", "--showuse", "--showmeminfo", "vram"],
        "sample_interval_seconds": 0.5,
        "sample_count": len(samples),
        "available_sample_count": len(available),
        "telemetry_available": bool(available and (vram or gpu_use)),
        "peak_vram_used_bytes": max(vram) if vram else None,
        "mean_vram_used_bytes": statistics.mean(vram) if vram else None,
        "peak_gpu_use_percent": max(gpu_use) if gpu_use else None,
        "mean_gpu_use_percent": statistics.mean(gpu_use) if gpu_use else None,
        "samples": samples,
    }


async def run_local_full(
    baseline_concurrency: int,
    optimized_concurrency: int,
    warmups: int,
) -> dict[str, Any]:
    privacy = await asyncio.to_thread(run_check)
    environment = await asyncio.to_thread(build_manifest)
    scenarios = load_scenario_set().scenarios
    samples: list[dict[str, Any]] = []
    stop = asyncio.Event()
    sampler = asyncio.create_task(_sampler(stop, samples))
    try:
        suite = await run_suite(
            _resolve_provider("radeon_local"),
            scenarios,
            baseline_concurrency,
            optimized_concurrency,
            warmups,
        )
    finally:
        stop.set()
        await sampler
    suite["privacy_egress_evidence"] = privacy
    suite["environment_manifest"] = environment
    suite["resource_metrics"] = _summarize_resources(samples)
    suite["run_mode"] = "local_radeon_rocm_full_cp101"
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run CP-101 end to end on a loopback Radeon/ROCm model endpoint, including "
            "privacy evidence, exact environment capture, fixed 48-scenario baseline and "
            "concurrent-serving optimization, token usage, GPU use and VRAM sampling."
        )
    )
    parser.add_argument("--baseline-concurrency", type=int, default=1)
    parser.add_argument("--optimized-concurrency", type=int, default=4)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/amd/results/local_radeon_cp101_full.json"),
    )
    args = parser.parse_args()
    if args.baseline_concurrency < 1 or args.optimized_concurrency < 1:
        parser.error("concurrency values must be at least 1")
    if args.warmups < 0:
        parser.error("warmups must be non-negative")

    payload = asyncio.run(
        run_local_full(
            args.baseline_concurrency,
            args.optimized_concurrency,
            args.warmups,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    print(
        json.dumps(
            {
                "comparison": payload["comparison"],
                "privacy_pass": payload["privacy_egress_evidence"]["pass"],
                "telemetry_available": payload["resource_metrics"][
                    "telemetry_available"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
