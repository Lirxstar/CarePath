from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .harness import BaselineRunner, EvaluationHarness
from .measured import measured_mock_runners
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
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--recorded-input",
        type=Path,
        help="JSONL containing one BaselineOutput per scenario and baseline.",
    )
    source.add_argument(
        "--measured-mock",
        action="store_true",
        help=(
            "Execute all four baselines with the repository mock provider and measured "
            "end-to-end latency."
        ),
    )
    parser.add_argument(
        "--benchmark-valid",
        action="store_true",
        help="Mark a measured or recorded synthetic engineering run as benchmark-valid.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        args.benchmark_valid
        and args.recorded_input is None
        and not args.measured_mock
    ):
        parser.error("--benchmark-valid requires --recorded-input or --measured-mock")

    runners: Sequence[BaselineRunner]
    if args.measured_mock:
        runners = measured_mock_runners()
        execution_mode = "measured_mock_provider"
        benchmark_valid = args.benchmark_valid
    elif args.recorded_input is not None:
        runners = load_recorded_runners(
            args.recorded_input,
            require_measured_latency=args.benchmark_valid,
        )
        execution_mode = "recorded_baseline_outputs"
        benchmark_valid = args.benchmark_valid
    else:
        runners = reference_runners()
        execution_mode = "deterministic_reference_fixture"
        benchmark_valid = False

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
