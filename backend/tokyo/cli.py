"""Command-line entrypoint for the CP-201 Tokyo open-data layer."""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from backend.tokyo.pipeline import build_resources, fetch_payloads, write_artifacts
from backend.tokyo.registry import load_registry

DEFAULT_REGISTRY = Path("data/tokyo/sources.json")
DEFAULT_OUTPUT = Path("data/tokyo/generated/resources.jsonl")
DEFAULT_REPORT = Path("data/tokyo/generated/build_report.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the bounded CarePath Tokyo resource corpus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry", help="validate source metadata only")
    validate.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)

    refresh = subparsers.add_parser("refresh", help="fetch official sources and rebuild artifacts")
    refresh.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    refresh.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    refresh.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    refresh.add_argument("--raw-dir", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_registry(args.registry)
    if args.command == "validate-registry":
        print(f"validated {len(registry.sources)} Tokyo source definitions")
        return 0
    if args.command == "refresh":
        with httpx.Client(headers={"User-Agent": "CarePath-CP201/1.0"}) as client:
            payloads, urls = fetch_payloads(registry, client=client, raw_dir=args.raw_dir)
        resources, report = build_resources(registry, payloads, urls)
        errors = [result for result in report.source_results if result.error]
        if errors:
            details = "; ".join(f"{item.source_id}: {item.error}" for item in errors)
            raise SystemExit(f"Tokyo resource build failed: {details}")
        if not resources:
            raise SystemExit("Tokyo resource build produced no resources")
        write_artifacts(resources, report, output_path=args.output, report_path=args.report)
        print(f"built {len(resources)} resources from {len(registry.sources)} sources")
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
