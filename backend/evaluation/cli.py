from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .harness import EvaluationHarness
from .recorded import load_recorded_runners
from .reference import reference_runners
from .scenarios import load_scenario_set


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed CarePath B0-B3 evaluation interface."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/results/reference-fixture-v1"),
    )
    parser.add_argument("--run-id", default="reference-fixture-v1")
    parser.add_argument(
        "--recorded-input",
        type=Path,
        help="JSONL containing one BaselineOutput per scenario and baseline.",
    )
    parser.add_argument(
        "--benchmark-valid",
        action="store_true",
        help="Mark a recorded run as benchmark-valid; requires measured latency.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.benchmark_valid and args.recorded_input is None:
        parser.error("--benchmark-valid requires --recorded-input")

    if args.recorded_input is None:
        runners = reference_runners()
        execution_mode = "deterministic_reference_fixture"
        benchmark_valid = False
    else:
        runners = load_recorded_runners(
            args.recorded_input,
            require_measured_latency=args.benchmark_valid,
        )
        execution_mode = "recorded_baseline_outputs"
        benchmark_valid = args.benchmark_valid

    run = EvaluationHarness(runners).run(
        load_scenario_set(),
        output_dir=args.output_dir,
        run_id=args.run_id,
        execution_mode=execution_mode,
        benchmark_valid=benchmark_valid,
    )
    print(json.dumps(run.summary.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
