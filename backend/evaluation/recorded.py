from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .harness import BaselineId, BaselineOutput, LatencySource
from .scenarios import EvaluationScenario


class RecordedBaselineRunner:
    def __init__(
        self,
        baseline_id: BaselineId,
        outputs: dict[str, BaselineOutput],
    ) -> None:
        self.baseline_id = baseline_id
        self.outputs = dict(outputs)

    def run(self, scenario: EvaluationScenario) -> BaselineOutput:
        try:
            return self.outputs[scenario.scenario_id]
        except KeyError as exc:
            raise ValueError(
                f"missing recorded output for {self.baseline_id}:{scenario.scenario_id}"
            ) from exc


def load_recorded_runners(
    path: Path,
    *,
    require_measured_latency: bool = False,
) -> tuple[RecordedBaselineRunner, ...]:
    grouped: dict[BaselineId, dict[str, BaselineOutput]] = defaultdict(dict)
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        output = BaselineOutput.model_validate_json(line)
        if output.scenario_id in grouped[output.baseline_id]:
            raise ValueError(
                f"duplicate recorded output at line {line_number}: "
                f"{output.baseline_id}:{output.scenario_id}"
            )
        if require_measured_latency and output.latency_source is not LatencySource.MEASURED:
            raise ValueError(
                "benchmark-valid run requires measured latency: "
                f"{output.baseline_id}:{output.scenario_id}"
            )
        grouped[output.baseline_id][output.scenario_id] = output

    missing = [baseline.value for baseline in BaselineId if baseline not in grouped]
    if missing:
        raise ValueError(f"recorded outputs are missing baselines: {missing}")
    return tuple(
        RecordedBaselineRunner(baseline_id, grouped[baseline_id])
        for baseline_id in BaselineId
    )
