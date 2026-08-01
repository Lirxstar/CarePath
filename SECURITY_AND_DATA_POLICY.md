# Security and Data Policy

## Purpose

This policy governs repository content for CarePath. It complements the safety boundary and non-goals in `PROJECT_SCOPE.md`.

This project is a research prototype, not clinical validation, and must not be represented as clinically validated or clinically effective.

## Content prohibited from Git

The repository must not contain:

- passwords;
- API keys;
- access or refresh tokens;
- credentials;
- private keys or private certificates;
- identifiable or private health data;
- real patient data without explicitly approved governance;
- unapproved model weights or checkpoints;
- large generated artifacts that do not belong in Git;
- full copyrighted clinical guidelines or other source material whose usage and redistribution rights have not been confirmed.

If a secret is committed, removing it from the current tree is not sufficient. Stop using it, rotate or revoke it, assess exposure, and coordinate an appropriate history cleanup without publishing the secret value.

## Health data

Use synthetic or openly licensed data for the frozen prototype. Generated datasets must be reproducible from version-controlled code and documented seeds. Keep schemas, generators, evaluation scenarios, configuration, and reproducibility metadata in Git; keep private or large generated outputs in the narrowly ignored locations documented by `.gitignore`.

Logs, screenshots, examples, fixtures, and bug reports must also be free of identifiable health information and unintended real-user data.

## External evidence documents

Prefer committing:

- source metadata;
- bibliographic references and stable identifiers;
- source URLs where appropriate;
- licence and redistribution notes;
- ingestion scripts;
- content hashes;
- reproducible retrieval procedures.

Do not commit full third-party evidence or clinical-guideline content when redistribution rights are uncertain. A publicly accessible URL does not by itself establish redistribution permission.

## Models and generated artifacts

Do not commit model weights, checkpoints, embeddings, vector-store exports, or large generated outputs unless the repository owner explicitly approves their purpose, licence, size, and distribution method. Record external model identifiers, versions, licences, and reproducible acquisition procedures instead.

## Safety boundary

Repository code, documentation, tests, and examples must preserve the frozen CarePath rules:

- no definitive diagnosis;
- no instruction to start, stop, or change medication;
- no representation as an emergency service;
- no claim that synthetic evaluation demonstrates clinical performance;
- deterministic safety triage remains outside the language model;
- uncertain, missing, or conflicting data must lower stated certainty.

## Reporting

Report a suspected secret or private-data exposure privately to the repository owner. Do not paste sensitive values into issues, pull requests, chat, logs, or screenshots. Security reports and debugging logs must be sanitized before sharing.
