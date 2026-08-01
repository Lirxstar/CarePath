---
name: Scope change proposal
about: Propose work outside the frozen PROJECT_SCOPE.md
title: "[Scope change] "
labels: scope-review
assignees: ""
---

## Scope Change Gate

`PROJECT_SCOPE.md` is the canonical frozen scope. New feature requests must begin with the `scope-review` label, remain in Backlog, and must not enter Ready or implementation until the Scope Change Gate is satisfied and the approved change is written into `PROJECT_SCOPE.md`.

Answer all six canonical questions:

1. Which B requirement or frozen success criterion does it directly support?
2. What existing acceptance criterion is currently impossible without it?
3. Can the same objective be met with a smaller implementation?
4. What is its estimated implementation, testing, documentation and debugging cost?
5. Which currently scheduled issue will be delayed or removed?
6. Does it introduce a new data category, clinical claim, safety risk, platform, model-training method, or external dependency?

## Proposed decision

<!-- Approve the smallest viable change, defer as P3-post-B, or reject. Explain how the PROJECT_SCOPE.md decision rule is met. -->

## Required scope-document update

<!-- Identify the exact PROJECT_SCOPE.md section that would change if approved. No implementation begins before that update is accepted. -->
