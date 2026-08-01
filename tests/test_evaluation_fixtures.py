import hashlib
from pathlib import Path

from data.evaluation.generate_fixtures import generate_all, load_catalog
from data.evaluation.validate_fixtures import REQUIRED_FILES, REQUIRED_PLOTS, validate_all


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_catalog_contains_ten_named_scenarios() -> None:
    catalog = load_catalog()
    scenarios = catalog["scenarios"]
    assert len(scenarios) == 10
    scenario_ids = {scenario["id"] for scenario in scenarios}
    assert scenario_ids == {
        "irregular_sleep_grad_student",
        "sedentary_remote_worker",
        "high_stress_office_worker",
        "return_to_activity",
        "mild_fall_risk_older_adult",
        "structured_missingness_user",
        "stable_metrics_subjective_discomfort",
        "low_adherence_user",
        "recovery_after_disruption",
        "balanced_routine_user",
    }
    assert all(3 <= len(scenario["ground_truth_sentences"]) <= 5 for scenario in scenarios)
    assert all(scenario["expected_findings"] for scenario in scenarios)


def test_all_persona_packages_generate_and_validate(tmp_path: Path) -> None:
    output = tmp_path / "fixtures"
    generate_all(output)
    validate_all(output)

    packages = sorted(path for path in output.iterdir() if path.is_dir())
    assert len(packages) == 10
    for package in packages:
        assert {path.name for path in package.iterdir() if path.is_file()} >= REQUIRED_FILES
        plots = package / "plots"
        assert {path.name for path in plots.iterdir() if path.is_file()} >= REQUIRED_PLOTS


def test_fixture_generation_is_exactly_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_all(first, seed=101, days=30)
    generate_all(second, seed=101, days=30)
    assert _tree_hash(first) == _tree_hash(second)


def test_different_seed_changes_fixture_content(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_all(first, seed=101, days=30)
    generate_all(second, seed=102, days=30)
    assert _tree_hash(first) != _tree_hash(second)
