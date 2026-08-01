# CP-005 Longitudinal Analysis Tools

## Scope

CP-005 provides deterministic health-behaviour analytics. These functions calculate trends and adherence from structured records. They do not diagnose disease or provide clinical risk predictions.

## Time-series tools

### compare_periods

Compares a recent configurable window against a previous or baseline window.

Outputs:

- current mean
- baseline mean
- absolute change
- relative/percentage change when baseline is non-zero
- coverage and missingness
- date ranges
- source observation IDs

If baseline mean is zero, percentage change is not produced.

### compute_trend

Computes a linear slope using calendar-day coordinates. Missing dates are not compressed into consecutive indexes.

Supports seven-day and twenty-eight-day windows.

### rolling_mean

Produces configurable rolling summaries. Minimum observation and coverage requirements are explicit.

### summarise_missingness

Missingness includes expected gaps based on configured observation frequency, not only explicit missing rows.

## Reliability

Reliability describes analytical data quality:

- sample size
- coverage
- suspect observations
- conflicting observations
- baseline availability

It is not medical confidence.

## Provenance

All outputs retain source observation IDs so later Context Builder, Planner, Verifier and Audit components can trace calculations back to original records.

## Adherence

Adherence is calculated from structured feedback states:

- completed = 1.0
- partially completed = completion ratio
- not completed = 0.0
- rejected = 0.0
- modified = provided completion ratio

Outputs retain plan, action and feedback identifiers.

## Safety boundary

Change signals indicate behavioural/statistical changes only. They are not clinical abnormalities and should not be interpreted as diagnoses.
