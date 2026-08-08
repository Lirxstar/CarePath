# CarePath issue board

This file is a lightweight repository mirror of the canonical GitHub issue backlog. GitHub Issues remain the source of truth for live task state.

## B core

| ID | Task | Priority | Status |
| --- | --- | --- | --- |
| CP-019 | Containerise and deploy backend | P1-required | Repository deployment complete; public cloud URL pending |
| CP-020 | Deploy reviewer-facing client | P1-required | Open; blocked by public CP-019 backend deployment |
| CP-021 | Produce B README and architecture diagram | P1-required | Open |
| CP-022 | Produce B technical report and demo | P0-application-blocking | Open |

## Extension tracks

Extension work remains isolated from the B core until its canonical dependencies and hardware or data requirements are satisfied.

- CP-101 and CP-102 cover the optional local-accelerator extension and submission package.
- CP-201 and CP-202 cover the bounded municipal open-data and multilingual-resource extension.

## CP-019 repository status

PR #33, `CP-019 containerise and deploy backend`, is merged into `main` as `10d53eac9b798912060f735d19529dd2610a01ad`.

Completed and CI-verified repository work:

- production non-root backend Docker image;
- PostgreSQL Docker Compose stack with persistent volumes and health-gated startup;
- automatic Alembic migration to head before API startup;
- `/health/live` and dependency-aware `/health/ready` probes;
- deployment environment and health-check documentation;
- cloud deployment blueprint using managed PostgreSQL;
- public deployment verification script;
- dedicated CP-019 Compose smoke workflow.

The canonical CP-019 issue remains open until an actual public cloud backend is created and `python deployment/verify_backend.py <PUBLIC_URL>` succeeds. A repository configuration alone is not evidence that the cloud service is accessible.
