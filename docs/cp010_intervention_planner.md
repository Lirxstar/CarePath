# CP-010 intervention planner and adaptation

CP-010 turns the CP-009 `PLANNER` and `FEEDBACK_UPDATE` stages into a persisted,
deterministic intervention-planning loop. It reuses the CP-002 canonical plan models, the
CP-004 SQLAlchemy storage tables, and CP-005 structured adherence signals rather than adding a
parallel schema.

## Seven-day plan contract

`backend.personalization.planner.InterventionPlanner.build_seven_day_plan` returns a
`SevenDayPlan` containing:

- one canonical `InterventionPlan` whose `end_date` is exactly six days after `start_date`;
- seven canonical `PlanAction` records, one for each calendar day in the plan;
- a `PlanAdaptation` trace containing the direction, reason codes, and source action/feedback IDs
  used for adaptation.

The daily action seed is supplied by the application as a `DailyActionTemplate`. CP-010 does not
let free-form external evidence modify safety policy, permissions, or persistence rules.

A generated plan remains structured data. The CP-009 workflow can serialize it with
`SevenDayPlan.model_dump(mode="json")` for the planner draft before the verifier/composer stages.
The application should call `persist_plan` only for the plan version it accepts for use.

## Persistence

`persist_plan` writes the canonical plan and seven actions to the existing
`intervention_plans` and `plan_actions` tables. When a new version supersedes a previous plan for
the same user and goal, the previous row is marked `superseded` and the new plan stores the
`supersedes_plan_id` link.

`record_feedback` writes `PlanFeedback` to `plan_feedback` and mirrors its outcome onto the
corresponding action status. The supported canonical outcomes are:

- `accepted`;
- `rejected`;
- `modified`;
- `completed`;
- `partially_completed`;
- `not_completed`.

Ownership is checked before plan generation and before feedback is written, so a goal,
interaction, or action belonging to another user cannot be used to create or update the plan.

## Adaptation rule

Adaptation reads the most recent persisted plan for the goal, its actions, and its structured
feedback. Limiting the explicit adaptation gate to the latest plan prevents an old rejection from
shrinking every later plan indefinitely.

The planner calls the CP-005 `summarise_adherence` and `difficulty_signal` functions. In addition,
it enforces the frozen `PROJECT_SCOPE.md` behaviour:

- one `rejected` action changes the next plan immediately;
- repeated non-completion changes the next plan after the CP-005 repeated-failure pattern is
  detected;
- the source action and feedback IDs that caused the revision are retained in `PlanAdaptation`.

The repeated-failure patterns are:

- `repeated_non_completion_or_rejection`;
- `consecutive_non_completion_or_rejection`.

A rejection or repeated failure forces the next action to become smaller or different:

- high difficulty becomes medium;
- medium difficulty becomes low;
- low difficulty stays low but switches to the configured alternative description, then the easier
  description, or a generated low-effort alternative when neither was supplied.

For medium/high actions, a configured easier description replaces the prior description on a
reduction. Every adaptation records the structured feedback/action IDs that caused it.

CP-005 may also recommend an increase after stable high completion. CP-010 applies that signal by
moving low to medium or medium to high while leaving the action content unchanged.

## Automated acceptance scenario

`tests/storage/test_intervention_planner.py` covers the Issue #10 acceptance criteria and the
stricter frozen-scope rejection rule:

1. exact seven-day structure with seven scheduled actions;
2. persistence of plans/actions and accepted, rejected, and not-completed feedback;
3. a single rejected action triggering a smaller next action with provenance IDs;
4. a rejected low-difficulty action switching to a different alternative;
5. repeated non-completion triggering a lower-difficulty next action;
6. an end-to-end scenario that persists plan version 1, records failure feedback, builds and
   persists version 2, marks version 1 superseded, and verifies the adapted action persisted.

The tests use the existing rollback-backed SQLite fixture and therefore exercise the same ORM
models used by the application storage layer.
