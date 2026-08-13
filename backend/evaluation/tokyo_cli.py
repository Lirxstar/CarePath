from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from backend.evaluation.tokyo import (
    DEFAULT_SCENARIO_PATH,
    run_tokyo_evaluation_path,
    write_tokyo_evaluation_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed CP-207 CarePath Tokyo engineering evaluation."
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=DEFAULT_SCENARIO_PATH,
        help="Version-controlled CP-207 scenario JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/tokyo/results"),
        help="Directory for results.json and summary.md.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_tokyo_evaluation_path(args.scenarios)
    write_tokyo_evaluation_report(report, args.output_dir)
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if report.threshold_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
