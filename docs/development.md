# Development environment

This guide is the reproducible local counterpart of
`.github/workflows/repository-quality.yml`. Run commands from the repository
root unless a section says otherwise.

## Reference toolchain

- Git
- Python 3.12 (the package metadata permits Python 3.11+, while CI uses 3.12)
- Node.js 22 and the npm version bundled with it

Check the active tools before installing dependencies:

```bash
git --version
python3.12 --version
node --version
npm --version
```

Do not use a global Python environment or `npm install` for CI reproduction.
The Python virtual environment isolates backend tools, and `npm ci` installs
the exact dependency tree recorded in `apps/mobile/package-lock.json`.

## Clean checkout setup

On macOS or Linux:

```bash
git clone https://github.com/repository-owner/CarePath.git
cd CarePath
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -c requirements-dev.lock -e '.[dev]'
npm --prefix apps/mobile ci
```

On Windows PowerShell:

```powershell
git clone https://github.com/repository-owner/CarePath.git
Set-Location CarePath
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -c requirements-dev.lock -e ".[dev]"
npm --prefix apps/mobile ci
```

`requirements-dev.lock` constrains the Python 3.12 reference dependency graph,
while `apps/mobile/package-lock.json` records the exact npm tree. Re-run the
corresponding install whenever either lock or `pyproject.toml` changes.

## Local environment variables

The backend only loads an environment file when `CAREPATH_ENV_FILE` points to
it. On macOS or Linux:

```bash
cp .env.example .env
export CAREPATH_ENV_FILE="$PWD/.env"
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
$env:CAREPATH_ENV_FILE = (Resolve-Path .env).Path
```

`.env` is ignored by Git. The committed example selects
`CAREPATH_LLM_PROVIDER=mock`; it does not require an API key, network access, or
an external model service. Never place a secret in a variable whose name starts
with `EXPO_PUBLIC_`, because Expo exposes those values to the client bundle.

## Run and inspect the backend

Start FastAPI:

```bash
python -m uvicorn backend.api.app.main:app \
  --host 127.0.0.1 --port 8000 --reload --no-access-log
```

From another terminal:

```bash
curl -fsS http://127.0.0.1:8000/health
```

The mock provider returns:

```json
{"status":"ok","provider":"mock"}
```

## Quality commands

These commands match CI. Run the complete group before opening a pull request.

Backend:

```bash
python -m pip check
python -m pre_commit validate-config .pre-commit-config.yaml
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
```

To apply Python formatting before re-running the checks:

```bash
python -m ruff format .
```

Frontend:

```bash
npm --prefix apps/mobile run format:check
npm --prefix apps/mobile run lint
npm --prefix apps/mobile run typecheck
npm --prefix apps/mobile run test:ci
```

To apply frontend formatting:

```bash
npm --prefix apps/mobile run format
```

Pytest and Jest enforce their configured coverage thresholds. The backend
health test uses an injected provider, and the provider contract tests use the
deterministic mock, so the test suite does not need credentials or a model
endpoint.

## Git hooks

The repository uses local `language: system` hooks. Install the Python and npm
dependencies first, keep the project virtual environment active while
committing or pushing, then install both hook stages:

```bash
python -m pre_commit install --hook-type pre-commit
python -m pre_commit install --hook-type pre-push
```

The commit hook runs Ruff formatting and linting, mypy, Prettier, ESLint, and
the TypeScript compiler for relevant staged files. The push hook runs the
backend and frontend test suites.

Run both stages across the checkout without making a commit:

```bash
python -m pre_commit run --all-files
python -m pre_commit run --hook-stage pre-push --all-files
```

## Continuous integration

`Repository quality` runs for every branch push, every pull request update, and
manual `workflow_dispatch` runs. The read-only workflow starts two independent
jobs:

- `Backend quality`: install, dependency and pre-commit configuration
  validation, Ruff formatting, Ruff lint, mypy, and pytest with coverage.
- `Frontend quality`: clean npm install, Prettier, ESLint, TypeScript, and Jest
  with coverage.

No CI secret is required because the backend job explicitly selects the mock
provider and the test environment.

## Verify that failures are detected

Only perform these checks on a disposable branch that you own. Never inject a
failure on `main`. Each probe creates one explicitly named file, so recovery
does not touch unrelated work.

Create a branch:

```bash
git switch -c ci/quality-gate-probe
```

### Formatting failure

Create an intentionally unformatted Python file:

```bash
printf 'def intentionally_bad( )->None:  print("probe")\n' \
  > backend/api/app/_ci_format_probe.py
python -m ruff format --check backend/api/app/_ci_format_probe.py
```

The command must return a non-zero status. For a local-only probe, remove the
file:

```bash
rm backend/api/app/_ci_format_probe.py
```

To prove the hosted workflow, commit and push the probe instead, confirm that
`Backend quality / Check Python formatting` fails, then recover with a revert:

```bash
git add backend/api/app/_ci_format_probe.py
git commit -m "test: inject formatting failure"
git push -u origin ci/quality-gate-probe
git revert --no-edit HEAD
git push
```

### Test failure

Create a deterministic failing test:

```bash
printf 'def test_ci_failure_probe() -> None:\n    assert False, "intentional CI probe"\n' \
  > tests/test_ci_failure_probe.py
python -m pytest
```

Pytest must return a non-zero status. For a local-only probe:

```bash
rm tests/test_ci_failure_probe.py
```

For a hosted check, commit and push the probe, confirm that
`Backend quality / Test Python` fails, then revert and push:

```bash
git add tests/test_ci_failure_probe.py
git commit -m "test: inject test failure"
git push
git revert --no-edit HEAD
git push
```

After either revert, both CI jobs must be green on the new commit. The failed
and successful GitHub Actions run URLs are the evidence that both the trigger
and quality gate work.
