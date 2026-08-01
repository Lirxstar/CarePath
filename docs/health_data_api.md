# Health data API

The CarePath FastAPI surface exposes canonical CP-002 health records for mobile and Agent use. All request bodies are validated by Pydantic, all controlled failures use the CarePath error envelope, and every response receives the configured request-ID header.

## Endpoints

- `POST /profiles` — create a canonical `UserProfile`.
- `GET /profiles/{user_id}` — read a profile.
- `POST /observations/batch` — atomically write 1–500 canonical `Observation` records.
- `GET /observations` — read observations for one user in a timezone-aware date range.
- `POST /journals` — write one canonical `JournalEntry`.
- `POST /goals` — create one canonical `Goal`.
- `GET /plans/current` — read the current active plan.
- `GET /plans/history` — read plan versions and their actions.

The existing `/records/import` and `/fhir/bundle` endpoints remain the bulk package import paths.

## Validation and limits

`Observation` validation is canonical: units must match the metric, numeric values must be finite, steps cannot be negative or fractional, sleep duration must be within 0–24 hours, score metrics must be 1–10, and event observations use boolean values with no unit.

`POST /observations/batch` is atomic. Duplicate IDs inside the batch, IDs already persisted, or a missing referenced profile cause a controlled 4xx response before any row is inserted.

`GET /observations` requires `start_at` and `end_at` with timezones. The maximum range is 366 days. `limit` is 1–100 and `offset` must be non-negative. `GET /plans/history` uses a 1–100 page limit.

## Error envelope and request ID

Controlled errors use:

```json
{
  "error": {
    "code": "stable_code",
    "message": "bounded message",
    "request_id": "correlation-id"
  }
}
```

A valid caller-supplied `X-Request-ID` is propagated; otherwise the API creates one. Operational logging records route, status, timing, component and bounded error metadata without logging request bodies or authorization data.

## OpenAPI

Run the API with one command from the repository root:

```bash
python -m uvicorn backend.api.app.main:app --host 127.0.0.1 --port 8000
```

OpenAPI JSON is available at `http://127.0.0.1:8000/openapi.json`; Swagger UI is available at `http://127.0.0.1:8000/docs`.

## curl examples

Create and read a profile:

```bash
USER_ID=11111111-1111-4111-8111-111111111111

curl -sS -X POST http://127.0.0.1:8000/profiles \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-profile-create' \
  -d "{\"user_id\":\"${USER_ID}\",\"age_band\":\"30-44\",\"preferred_language\":\"en\",\"timezone\":\"UTC\",\"health_goals\":[\"sleep\",\"physical_activity\"],\"consent_flags\":{\"synthetic_data\":true}}"

curl -sS "http://127.0.0.1:8000/profiles/${USER_ID}"
```

Write observations atomically:

```bash
curl -sS -X POST http://127.0.0.1:8000/observations/batch \
  -H 'Content-Type: application/json' \
  -d "{\"observations\":[{\"observation_id\":\"22222222-2222-4222-8222-222222222222\",\"user_id\":\"${USER_ID}\",\"metric_type\":\"steps\",\"value_numeric\":6500,\"value_boolean\":null,\"unit\":\"steps\",\"observed_at\":\"2026-07-30T08:00:00+00:00\",\"source_type\":\"synthetic_wearable\",\"quality_flag\":\"valid\",\"confidence\":0.95,\"metadata\":{\"synthetic\":true}}]}"
```

Read a bounded range with pagination:

```bash
curl -sS --get http://127.0.0.1:8000/observations \
  --data-urlencode "user_id=${USER_ID}" \
  --data-urlencode 'start_at=2026-07-01T00:00:00+00:00' \
  --data-urlencode 'end_at=2026-07-31T23:59:59+00:00' \
  --data-urlencode 'metric_type=steps' \
  --data-urlencode 'limit=50' \
  --data-urlencode 'offset=0'
```

Write a journal entry and create a goal:

```bash
curl -sS -X POST http://127.0.0.1:8000/journals \
  -H 'Content-Type: application/json' \
  -d "{\"entry_id\":\"33333333-3333-4333-8333-333333333333\",\"user_id\":\"${USER_ID}\",\"created_at\":\"2026-07-30T09:00:00+00:00\",\"text\":\"Synthetic check-in\",\"language\":\"en\",\"user_tags\":[\"synthetic\"]}"

curl -sS -X POST http://127.0.0.1:8000/goals \
  -H 'Content-Type: application/json' \
  -d "{\"goal_id\":\"44444444-4444-4444-8444-444444444444\",\"user_id\":\"${USER_ID}\",\"domain\":\"sleep\",\"description\":\"Keep a regular sleep schedule\",\"status\":\"active\",\"created_at\":\"2026-07-30T09:00:00+00:00\",\"target_date\":\"2026-08-30\"}"
```

Read plan history:

```bash
curl -sS --get http://127.0.0.1:8000/plans/history \
  --data-urlencode "user_id=${USER_ID}" \
  --data-urlencode 'limit=20' \
  --data-urlencode 'offset=0'
```
