# CP-012 FastAPI contract

CP-012 exposes the frozen B backend surface from `PROJECT_SCOPE.md` without duplicating the underlying CP-002/004/005/009/010/011 business logic.

## Frozen endpoints

- `POST /profiles`
- `POST /records/import`
- `POST /fhir/bundle`
- `GET /records/trends`
- `POST /coach/message`
- `GET /plans/current`
- `POST /plans/{plan_id}/feedback`
- `GET /audit/{interaction_id}`
- `GET /health`

All endpoints are included in FastAPI OpenAPI output. Request bodies and query/path parameters use typed Pydantic/FastAPI validation. Validation failures, not-found errors, conflicts, and unhandled failures use the existing structured CarePath error envelope and request correlation ID.

## Transport decisions

### Profile

`POST /profiles` accepts the canonical CP-002 `UserProfile` object and persists it through the CP-004 SQLAlchemy schema. Duplicate `user_id` values return a controlled `409 profile_exists` error.

### CSV and project JSON import

`POST /records/import` uses a JSON transport envelope:

```json
{
  "source_format": "csv | json",
  "content": "CSV text, or a JSON object for project JSON"
}
```

The endpoint delegates validation and atomic persistence to the CP-004 importers and `ImportService`; the response is the existing structured `ImportReport`.

### Limited FHIR

`POST /fhir/bundle` accepts a typed root Bundle contract and delegates supported Patient, Observation, Goal, and CarePlan handling to the CP-004 limited FHIR importer. This remains intentionally narrower than a FHIR server.

### Trends

`GET /records/trends` requires `user_id` and `metric_type`; `days` is bounded to 1–60 and defaults to seven. It delegates trend and previous-window comparison calculations to CP-005 deterministic analytics and preserves source observation IDs in the result.

### Coach interaction

`POST /coach/message` returns a stable `interaction_id`, request correlation ID, risk level, workflow status, controlled response text, evidence IDs, and verifier disposition. CP-012 wires the frozen CP-009 state machine with CP-011 verification in a deliberately evidence-empty contract composition. This validates orchestration, safety gating, interaction persistence, bounded verification, and the HTTP schema without fabricating a coaching plan when a runtime personal/external evidence composition is not yet configured.

The full reviewer-facing end-to-end composition remains downstream work for the mobile/user-journey issues; CP-012 does not create an unsupported model-only coaching path.

### Plan and feedback

`GET /plans/current` returns the latest active plan for a user, optionally scoped to a goal, together with its actions. `POST /plans/{plan_id}/feedback` validates plan/action ownership and delegates persistence/status updates to CP-010 `InterventionPlanner.record_feedback`.

### Audit

`GET /audit/{interaction_id}` exposes already-persisted `AuditEvent` rows in sequence order. CP-013 owns comprehensive ordered audit event creation and privacy-minimised audit population; CP-012 only establishes and tests the HTTP contract needed by CP-013.

## Error and correlation contract

Every request receives the configured request-ID response header (default `X-Request-ID`). Caller-supplied valid IDs round-trip; invalid IDs are replaced. Controlled errors use:

```json
{
  "error": {
    "code": "stable_code",
    "message": "bounded message",
    "request_id": "correlation-id"
  }
}
```

Raw exception messages, authorization headers, prompts, and request bodies are not added to operational logs by these routes.

## Acceptance tests

`tests/test_cp012_api_contract.py` verifies:

- every frozen path/method appears in OpenAPI;
- Pydantic validation and structured errors;
- request-ID propagation;
- profile creation and duplicate handling;
- CSV and project JSON import;
- limited FHIR Bundle import;
- deterministic trend and baseline comparison;
- coach interaction ID generation and persistence;
- current plan lookup and feedback persistence;
- ordered audit endpoint output.
