#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_CAPTURE_CHARS = 40_000
ROCMINFO_PREFIXES = (
    "Name:",
    "Marketing Name:",
    "Vendor Name:",
    "Device Type:",
    "Chip ID:",
    "Compute Unit:",
    "Max Queue Number:",
)


def run_command(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return {"available": False, "command": args}
    except subprocess.TimeoutExpired:
        return {"available": True, "command": args, "timed_out": True}

    return {
        "available": True,
        "command": args,
        "returncode": completed.returncode,
        "stdout": completed.stdout[:MAX_CAPTURE_CHARS],
        "stderr": completed.stderr[:MAX_CAPTURE_CHARS],
    }


def filtered_rocminfo() -> dict[str, Any]:
    result = run_command(["rocminfo"])
    stdout = result.get("stdout")
    if not isinstance(stdout, str):
        return result
    selected = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(ROCMINFO_PREFIXES):
            selected.append(stripped)
    result["stdout"] = "\n".join(selected)
    return result


def torch_environment() -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        return {"available": False}

    accelerator_available = torch.cuda.is_available()
    devices = []
    if accelerator_available:
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": torch.cuda.get_device_name(index),
                    "total_memory_bytes": properties.total_memory,
                    "architecture": getattr(properties, "gcnArchName", None),
                }
            )

    return {
        "available": True,
        "torch_version": torch.__version__,
        "hip_version": getattr(torch.version, "hip", None),
        "accelerator_available": accelerator_available,
        "device_count": torch.cuda.device_count() if accelerator_available else 0,
        "devices": devices,
    }


def git_commit() -> str | None:
    result = run_command(["git", "rev-parse", "HEAD"])
    if result.get("returncode") == 0:
        return str(result.get("stdout", "")).strip() or None
    return None


def build_manifest() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "captured_at": datetime.now(UTC).isoformat(),
        "carepath_commit": git_commit(),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "amd_stack": {
            "rocm_smi": run_command(
                [
                    "rocm-smi",
                    "--showproductname",
                    "--showdriverversion",
                    "--showmeminfo",
                    "vram",
                ]
            ),
            "rocminfo": filtered_rocminfo(),
        },
        "framework": {"pytorch": torch_environment()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture non-secret AMD/ROCm environment evidence for CarePath."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/amd/results/environment.json"),
    )
    args = parser.parse_args()

    manifest = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
