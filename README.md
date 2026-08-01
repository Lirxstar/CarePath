# CarePath

## What CarePath is

CarePath is a research-facing, safety-aware mobile health-coaching prototype. Its frozen B scope is to analyse longitudinal synthetic health-behaviour data across sleep, physical activity, stress and mood, and falls and activity safety. The planned system will combine personal observations with trusted public guidance to produce small, evidence-grounded behaviour-change plans, explicit uncertainty, safety boundaries, and an auditable interaction trace.

CarePath is not a medical service. It does not diagnose conditions, recommend treatment, or instruct users to start, stop, or change medication. The project has not been clinically validated and must not be represented as clinically effective.

## Current project status

### Implemented

- The canonical frozen scope and dependency-aware backlog are version controlled.
- Repository governance, contribution templates, safety/data policy, and initial quality gates are configured.
- The B, AMD, and Tokyo work streams are separated in the repository and GitHub Project.
- System, agent-state, trust-boundary and deployment architecture contracts are documented as maintained Mermaid sources.
- Safety, privacy, trust and data-use rules are expressed as test-ready normative requirements.
- A runnable FastAPI foundation provides Pydantic Settings configuration, structured errors, request IDs, metadata-only JSON logging and a replaceable `LLMProvider` with a development mock.

### In progress

- Canonical domain models and subsequent B Core application features remain in the dependency-aware backlog.

### Planned

- The React Native/Expo implementation, domain/data pipeline, CarePath agent workflow, evidence retrieval, safety engine, evaluation suite, and deployment implementations are planned in `ISSUE_BOARD.md`.
- AMD and Tokyo extensions remain inactive Post-B work.

## Project scope

[`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) is the canonical frozen scope. A feature that is not explicitly listed there must pass its six-question Scope Change Gate before implementation. Proposed scope changes remain in Backlog with the `scope-review` label and cannot enter Ready until the gate is satisfied.

## Backlog

[`ISSUE_BOARD.md`](ISSUE_BOARD.md) defines the initial implementation backlog, acceptance criteria, labels, dependencies, and work-in-progress policy. GitHub issues use stable identifiers from CP-001 through CP-022, CP-101 through CP-102, and CP-201 through CP-202.

## Architecture

The canonical architecture and module interfaces are documented in
[`docs/architecture.md`](docs/architecture.md). The implementation boundary consists of:

- a React Native/Expo mobile client;
- a FastAPI backend with the frozen API and data contracts;
- separate retrieval paths for personal context and external evidence;
- one bounded CarePath agent state graph with deterministic safety triage and verification;
- PostgreSQL as the target database, with SQLite allowed for local development;
- reproducible synthetic data and a fixed evaluation suite.

See `PROJECT_SCOPE.md` for the authoritative component boundaries and non-goals.

## Repository structure

```text
.
├── apps/mobile/                # Canonical shared React Native/Expo boundary
├── backend/api/                # Runnable shared FastAPI foundation
├── agents/                     # Shared bounded workflow boundary
├── safety/                     # Shared deterministic safety boundary
├── retrieval/                  # Shared personal/evidence retrieval boundary
├── timeseries/                 # Shared deterministic analytics boundary
├── personalization/            # Shared adaptation boundary
├── deployment/                 # Shared deployment boundary
├── data/                       # Data conventions and reproducible-data boundary
├── docs/                       # Project documentation
├── evaluation/                 # Planned fixed evaluation suite
├── tests/                      # Repository quality-gate tests
├── .github/                    # Issue/PR templates and CI
├── .pre-commit-config.yaml     # Local commit and push quality gates
├── ISSUE_BOARD.md              # Canonical dependency-aware backlog
├── PROJECT_SCOPE.md            # Canonical frozen project scope
└── SECURITY_AND_DATA_POLICY.md # Repository security and data rules
```

Shared core modules live once at repository root. AMD and Tokyo branches add
adapters or providers without duplicating these directories.

## Branch strategy

- `main`: canonical B Core development branch.
- `amd-track2`: reserved, inactive branch for the Post-B AMD Track 2 extension.
- `tokyo-open-data`: reserved, inactive branch for the Post-B Tokyo open-data extension.

Extension work must not weaken or delay B Core work.

## Development workflow

The workflow is:

```text
Issue → Ready → In Progress → Pull Request → Review → Done
```

Backlog contains in-scope work that is not yet dependency-ready. Blocked records active blockers. The work-in-progress limit is **2**. B Core work takes precedence, and Post-B work cannot begin while a P0 B issue is incomplete or blocked.

## GitHub Project

[CarePath Development Board](https://github.com/users/repository-owner/projects/1) is the single dependency-aware planning board. Its active Development Board is limited to the B Core phase; AMD and Tokyo issues remain in the Post-B Backlog.

## Safety and data policy

Repository contributors must not commit secrets, credentials, private keys, identifiable health information, real patient data without approved governance, unapproved model weights, or third-party clinical content with uncertain redistribution rights. Use synthetic or openly licensed data and keep external evidence reproducible through metadata, references, URLs, and ingestion procedures.

Read [`SECURITY_AND_DATA_POLICY.md`](SECURITY_AND_DATA_POLICY.md) before adding data, models, evidence documents, logs, or generated artifacts.

## Evaluation philosophy

CarePath is evaluation-driven. The frozen scope requires reproducible synthetic scenarios, deterministic safety fixtures, explicit baselines, traceable evidence identifiers, and reported failures and limitations. Internal thresholds are engineering acceptance criteria on synthetic test cases, not clinical validation.

## Development setup

The CI reference toolchain is Python 3.12 and Node.js 22. From the repository
root, create an isolated Python environment and install both dependency sets:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -c requirements-dev.lock -e '.[dev]'
npm --prefix apps/mobile ci
```

Create the untracked local environment file and select it explicitly:

```bash
cp .env.example .env
export CAREPATH_ENV_FILE="$PWD/.env"
```

The default mock provider requires no API key or external model service. Start
the backend:

```bash
python -m uvicorn backend.api.app.main:app \
  --host 127.0.0.1 --port 8000 --reload --no-access-log
```

In another terminal, verify the health endpoint:

```bash
curl -fsS http://127.0.0.1:8000/health
# {"status":"ok","provider":"mock"}
```

Install the local Git hooks after both dependency sets are installed:

```bash
python -m pre_commit install --hook-type pre-commit
python -m pre_commit install --hook-type pre-push
python -m pre_commit run --all-files
```

See [`docs/development.md`](docs/development.md) for the complete backend and
frontend quality commands, Windows environment setup, CI behaviour, and safe
failure-injection checks. Configuration uses `CAREPATH_`-prefixed environment
variables; `.env.example` documents every current setting.
