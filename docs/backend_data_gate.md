# Backend data/API Gate

This Gate is the entry condition for Agent-facing feature work that depends on stable health data, persistence, deterministic analysis and HTTP contracts.

## Scope

The repository quality workflow covers:

- CP-002 canonical schemas and validation;
- CP-004 SQLAlchemy storage, Alembic upgrade/downgrade, CRUD and CSV/JSON/FHIR imports;
- CP-005 deterministic time-series and adherence/personalization tools;
- FastAPI OpenAPI, request-ID, structured errors and health-data endpoints;
- ten-persona synthetic import/readback through the public API;
- absence of blocking TODO/FIXME markers and user-specific absolute paths in `backend/**/*.py`.

The complete test suite is required to stay above the configured 85% branch-coverage threshold. The suite contains substantially more than the minimum 15 automated tests.

## Ten-persona integration Gate

`tests/test_backend_data_gate.py` generates ten deterministic 30-day CP-003 personas and imports each one through `POST /records/import`. For every persona the Gate verifies:

1. import succeeds atomically;
2. the profile is readable through `GET /profiles/{user_id}`;
3. observations are readable through the bounded/paginated observation endpoint;
4. deterministic step trends are computable;
5. plan history and actions are readable;
6. generated plan/feedback data can be consumed by the CP-005 adherence and personalization contract;
7. `/health` starts and responds through the same FastAPI application.

## Reproduction

From a clean environment:

```bash
python -m pip install -c requirements-dev.lock -e '.[dev]'
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest --junitxml=test-results/pytest.xml
```

`pytest` also emits `coverage.xml` and fails if branch coverage falls below 85%.

## Saved reports

Every Repository quality run uploads the backend report artifact after the Python test step, including:

- `test-results/pytest.xml` — JUnit test report;
- `coverage.xml` — machine-readable coverage report.

The upload step runs even when tests fail so a failed Gate has inspectable evidence. A functional failure must be fixed or tracked explicitly; it must not be bypassed by lowering the coverage threshold, deleting acceptance tests or disabling the failing Gate.
