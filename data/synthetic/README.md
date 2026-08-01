# CP-003 Synthetic Longitudinal Dataset

## Purpose

Generate privacy-safe synthetic longitudinal health data for CarePath evaluation. No real person or patient data is used.

## Usage

```bash
python -m data.synthetic.generate --seed 42 --days 45 --output data/generated
```

Parameters:

- `--seed`: deterministic random seed. The same seed produces the same dataset.
- `--days`: number of days per persona. Valid range is 30-60.
- `--output`: destination directory for generated JSON and CSV files.

## Outputs

- `profile.json`: UserProfile records
- `observations.csv`: Observation records
- `journal_entries.json`: JournalEntry records
- `goals.json`: Goal records
- `intervention_history.json`: intervention plans, actions and feedback
- `ground_truth.json`: injected events and evaluation metadata

## Synthetic Design

The generator creates 10 personas with different baseline characteristics, languages, timezones, activity levels, stress patterns and adherence patterns.

Generated signals include:

- sleep duration
- steps
- active minutes
- resting heart rate
- stress score
- mood score
- activity confidence

The dataset includes:

- weekly periodicity
- persona-specific trends
- structured missingness with reasons
- injected change points
- explicit contradictions between observations and journals
- designed metric correlations

All generated records are validated against CP-002 canonical models.
