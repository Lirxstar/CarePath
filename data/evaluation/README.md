# CP-003A Audited Persona Evaluation Fixtures

## Purpose

CP-003A converts synthetic longitudinal data into deterministic demo and evaluation packages. The fixtures are designed for testing longitudinal pattern discovery, evidence retrieval, and safe health-behaviour support workflows.

## Generate

```bash
python -m data.evaluation.generate_fixtures --output data/evaluation/generated --seed 20260728 --days 45
```

Parameters:

- `--seed`: deterministic random seed. The same seed produces identical fixture contents.
- `--days`: observation duration. Supported range is 30–60 days.
- `--output`: destination directory for persona packages.

## Persona packages

The fixture set contains exactly ten named contexts:

1. irregular_sleep_grad_student
2. sedentary_remote_worker
3. high_stress_office_worker
4. return_to_activity
5. mild_fall_risk_older_adult
6. structured_missingness_user
7. stable_metrics_subjective_discomfort
8. low_adherence_user
9. recovery_after_disruption
10. balanced_routine_user

## Package contract

Each package contains:

- `profile.json`
- `observations.csv`
- `journal_entries.json`
- `goals.json`
- `intervention_history.json`
- `scenario.json`
- `ground_truth.json`
- `expected_findings.json`
- `audit.json`
- `plots/` SVG time-series files

## Audit

`validate_fixtures.py` checks:

- canonical schema compatibility;
- units and timestamps;
- missingness structure;
- metric ranges;
- scenario-specific patterns;
- ground truth consistency;
- expected Agent findings;
- time-series plot presence.

The fixtures are synthetic and are intended for evaluation and development only.
