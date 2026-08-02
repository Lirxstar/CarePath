from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from backend.evaluation.acceptance import (
    AcceptanceStatus,
    evaluate_acceptance,
    load_evaluation_run,
    write_acceptance_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply the frozen CP-018 engineering acceptance thresholds."
    )
    parser.add_argument(
        "evaluation_dir",
        type=Path,
        help="Directory containing manifest.json, summary.json, and raw_results.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report destination; defaults to the evaluation directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run = load_evaluation_run(args.evaluation_dir)
    report = evaluate_acceptance(run)
    write_acceptance_report(report, args.output_dir or args.evaluation_dir)
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    if report.status is AcceptanceStatus.PASS:
        return 0
    if report.status is AcceptanceStatus.FAIL:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
