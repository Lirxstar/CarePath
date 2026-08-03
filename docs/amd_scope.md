# AMD Track 2 Scope — CarePath Local Inference and Performance Extension

**Status:** FROZEN for development on `amd-track2`  
**Base product:** CarePath B main project on `main`  
**Competition:** AMD AI DevMaster Hackathon, Track 2  
**Track:** Development and local deployment of private AI agents  
**Submission deadline:** 2026-08-06 23:59 UTC+8  
**Canonical scope document:** `docs/amd_scope.md`

> **Scope rule:** The AMD branch is a hardware-specific local-inference and performance extension of the frozen CarePath B project. It is not a second product, a rewrite, or an independent research prototype.

## 1. Preconditions and decision record

The AMD extension may start only after the CarePath B P0 scope and its safety and evaluation thresholds are frozen. The current repository records the B scope as frozen in `PROJECT_SCOPE.md`, and the completed CP-018 acceptance record reports that all frozen B3 internal thresholds passed.

The implementation branch is:

```text
main
└── amd-track2
```

`amd-track2` must remain based on `main`. Shared fixes that are not AMD-specific should be implemented or upstreamed in `main`, then merged into `amd-track2`. AMD-only code must not be merged into `main` merely to simplify the competition submission.

## 2. Competition and eligibility status

### 2.1 Verified competition facts

| Item | Status | Evidence or required action |
|---|---|---|
| Competition | Verified | AMD AI DevMaster Hackathon |
| Selected track | Verified | Track 2: Development and Local Deployment of Private AI Agents |
| Agentic AI fit | Verified | CarePath already has a bounded agent workflow, tool selection, personal-context retrieval, evidence retrieval, safety verification, planning, and audit traces |
| Registration | Accepted | Connected calendar evidence records an accepted place for the hackathon |
| Registration mode | Solo unless the private Luma record names a team | The connected event contains one accepted participant; personal registration details must remain outside the public repository |
| Deadline | Verified | 2026-08-06 23:59 UTC+8 |
| Submission language | Verified | English |
| Official submission channel | Verified | Fork the official submission repository and open a pull request |
| AMD AI Developer Program membership | **Not independently verified — submission blocker** | No membership confirmation was found in the connected mailboxes. Verify active membership in the AMD developer account before submission |
| Rules and Conditions acceptance | **Not independently verified — submission blocker** | Review and accept the Rules and Conditions linked from the registration page before submission |

Official references:

- Event registration: <https://luma.com/amd-4dhi>
- AMD AI Developer Program: <https://developer.amd.com/ai-developer-program/>
- Official submission repository: <https://github.com/AMD-DEV-CONTEST/Radeon-hackathon-2026-07>

### 2.2 Team and identity handling

The current evidence supports a solo submission. The registered legal or personal name, email address, Luma access token, developer-account identifiers, and other private registration data must not be committed to this public repository.

Before submission, record the following in a private checklist:

- registered participant name;
- registered email address;
- AMD AI Developer Program membership status;
- Luma team name, if one was entered;
- confirmation that the same participant is represented in the final submission;
- acceptance of the current Rules and Conditions.

The official pull-request title must be:

```text
Track 2, <registered team name>, CarePath
```

If no team name was registered, use:

```text
Track 2, <registered participant name>, CarePath
```

## 3. Product boundary

CarePath on `main` remains the only product. The AMD branch reuses the same:

- React Native or Expo client;
- FastAPI backend and API contracts;
- domain models and synthetic data;
- personal-context and evidence-retrieval paths;
- bounded agent state graph;
- deterministic safety triage and verification;
- plan generation, feedback, and history workflow;
- evaluation scenarios and annotations;
- audit model and non-clinical safety boundaries.

The AMD branch may add exactly five categories of work:

1. **Radeon and ROCm local inference provider**
   - one implementation of the existing `LLMProvider` contract;
   - local model loading and generation on an AMD Radeon GPU through a supported ROCm or HIP runtime;
   - provider-specific configuration, startup validation, health metadata, and tests.

2. **Privacy mode**
   - a local-only execution mode in which prompts, personal context, retrieved evidence, generated plans, and audit payloads do not leave the host during inference;
   - fail-closed configuration when a remote endpoint is supplied while local-only mode is active;
   - explicit runtime evidence that inference completed without application-level network egress.

3. **Performance benchmark and reproducibility harness**
   - fixed benchmark inputs derived from the frozen CarePath evaluation set;
   - raw machine-readable results;
   - exact hardware and software manifests;
   - unoptimised and optimised Radeon comparisons.

4. **Optimisation implementation and explanation**
   - documented, measured changes to model format, precision, quantisation, context handling, runtime configuration, kernels, caching, or batching;
   - no optimisation may weaken the frozen safety, grounding, tool-selection, or output-contract behaviour.

5. **Competition materials**
   - English project specification;
   - English setup and reproduction instructions;
   - three-to-five-minute Radeon execution demo;
   - PPT or poster;
   - final official-repository pull request.

Anything outside these five categories is out of scope unless this document is explicitly revised before implementation.

## 4. Explicit non-goals

The AMD branch must not:

- copy `apps/mobile`, `backend`, `agents`, `safety`, `retrieval`, `timeseries`, `personalization`, or `evaluation` into a parallel product tree;
- create an independent application with a separate product name;
- add a new health domain, persona, data model, planning workflow, or agent architecture;
- replace the B safety rules, evidence requirements, output contract, or audit semantics;
- introduce diagnosis, treatment, medication, clinical-effectiveness, or clinical-validation claims;
- present a remote API or CPU-only run as the required Radeon execution;
- optimise latency by bypassing retrieval, safety verification, citations, structured output, or audit generation;
- add unrelated training, fine-tuning, UI redesign, social features, notification systems, or data integrations;
- retain or revive the former **ResearchRoom Verify** proposal.

`ResearchRoom Verify` is retired. It is not an alias, fallback concept, secondary demo, backlog item, architecture option, or submission narrative. Repository and submission checks must fail if `ResearchRoom` is found outside an explicit deprecation statement.

## 5. Architecture delta

The architectural change is deliberately narrow:

```text
CarePath mobile client
        |
        v
Existing FastAPI and CarePath agent workflow
        |
        v
Existing LLMProvider interface
        |
        +----------------------+
        |                      |
        v                      v
Existing mock/test provider    New Radeon/ROCm local provider
                               |
                               v
                       Local instruction model
                       on AMD Radeon GPU
```

The provider may change model execution, but it must not change the meaning of an agent state, tool result, safety decision, evidence reference, plan action, or audit record.

### 5.1 Proposed configuration contract

The exact names may be adjusted to existing settings conventions, but all settings must retain the `CAREPATH_` prefix.

```text
CAREPATH_LLM_PROVIDER=rocm_local
CAREPATH_MODEL_ID=<model identifier>
CAREPATH_MODEL_PATH=<optional local path>
CAREPATH_MODEL_REVISION=<immutable revision>
CAREPATH_ROCM_DEVICE=0
CAREPATH_INFERENCE_DTYPE=<fp16|bf16>
CAREPATH_QUANTIZATION=<none|supported format>
CAREPATH_MAX_CONTEXT_TOKENS=<integer>
CAREPATH_MAX_NEW_TOKENS=<integer>
CAREPATH_PRIVACY_MODE=local_only
CAREPATH_ALLOW_REMOTE_INFERENCE=false
```

No secret, access token, personal path, or registration identifier may be committed.

### 5.2 Provider acceptance criteria

The Radeon provider is complete only when it:

- implements the existing `LLMProvider` interface rather than adding a second inference abstraction;
- loads the selected model on the declared Radeon device;
- returns the same structured result shape expected by the existing agent workflow;
- supports deterministic or bounded generation settings suitable for evaluation;
- reports provider, model revision, runtime, device, precision, quantisation, and privacy mode through non-sensitive diagnostic metadata;
- validates ROCm or HIP availability and device compatibility at startup;
- emits an actionable error when the model cannot fit or the runtime is unsupported;
- fails closed if local-only privacy mode conflicts with any remote inference configuration;
- keeps the mock provider available for unit tests, but never substitutes it for the competition demonstration;
- passes existing provider, safety, workflow, and evaluation tests.

## 6. Model and runtime candidates

Candidates are evaluated rather than assumed. The final model must be selected from measured results on the actual Radeon environment.

| Priority | Model candidate | Intended role | Selection conditions |
|---:|---|---|---|
| 1 | `Qwen/Qwen2.5-7B-Instruct` | Primary full-capability candidate | Fits available VRAM; produces reliable structured output; passes frozen CarePath quality and safety gates |
| 2 | `meta-llama/Llama-3.1-8B-Instruct` | Reference alternative | Required model access and licence terms are satisfied; fits hardware; meets the same gates |
| 3 | `microsoft/Phi-4-mini-instruct` | Lower-memory and latency candidate | Provides acceptable tool and schema behaviour when the larger candidates do not meet latency or memory limits |

Runtime candidates, in evaluation order:

1. PyTorch and Transformers on the supported ROCm environment as the correctness baseline;
2. `llama.cpp` with the HIP backend for a quantised local path when the selected model and hardware are supported;
3. another AMD-supported inference runtime only when its Radeon compatibility is demonstrated and its environment is reproducible.

The final submission must identify one primary model and runtime. Other candidates may appear only as benchmark comparisons or documented fallbacks.

## 7. Hardware and software environment record

The exact competition hardware is not yet recorded in the repository. Development must not invent it. For every benchmark machine, save a manifest containing:

| Category | Required fields |
|---|---|
| GPU | exact Radeon model, device ID, architecture or GFX target, VRAM |
| Host | CPU, host RAM, storage type |
| Operating system | distribution, version, kernel |
| AMD stack | driver version, ROCm version, HIP version |
| Framework | Python, PyTorch, Transformers, runtime and accelerator-library versions |
| Model | repository ID, immutable revision, model format, precision, quantisation |
| Application | CarePath commit SHA, configuration hash, benchmark-data revision |
| Power mode | relevant GPU power or performance profile when available |

Target environments:

- **Official or organiser-provided Radeon environment:** required for the final recorded demonstration when available.
- **Local Radeon environment:** optional development and reproducibility target; record separately.
- **CPU or mock environment:** correctness reference only; never reported as the Track 2 performance result.

Recommended manifest path:

```text
evaluation/amd/results/<hardware-id>/environment.json
```

## 8. Benchmark protocol

### 8.1 Systems compared

Use the same CarePath commit and fixed scenarios for:

- `R0`: Radeon baseline, local model, no optional optimisation;
- `R1`: Radeon optimised configuration;
- optional runtime or model candidates, clearly labelled;
- mock provider only as a deterministic correctness reference, not a performance competitor.

### 8.2 Workload

- Use the frozen 48-scenario evaluation set or a version-controlled deterministic subset for rapid iteration.
- The final quality comparison must run all 48 scenarios.
- Use identical personal context, evidence corpus, prompts, tool outputs, generation limits, and safety rules across configurations.
- Run at least three warm-up requests before timing.
- Run at least five measured repetitions per designated latency scenario.
- Record failures and timeouts; do not discard them from aggregates.
- Save raw per-request results before producing summaries.

### 8.3 Performance metrics

| Metric | Unit or rule |
|---|---|
| Model load time | seconds |
| Cold end-to-end latency | seconds |
| Warm end-to-end latency | p50 and p95 seconds |
| Time to first token | p50 and p95 milliseconds |
| Decode throughput | tokens per second |
| Total generated tokens | tokens per request |
| Peak GPU memory | MiB or GiB |
| Peak host memory | MiB or GiB |
| GPU utilisation | sampled average and peak when available |
| Failure and timeout rate | percentage |
| Structured-output validity | percentage |
| Local inference coverage | percentage of model calls served locally |
| Application-level inference egress | must be zero in local-only mode |

### 8.4 Behaviour-preservation metrics

The AMD optimisation is acceptable only when it preserves the frozen CarePath evaluation intent. Report at minimum:

- scenario completion;
- safety escalation recall;
- tool-selection accuracy;
- patient-context fidelity;
- citation precision;
- unsupported medical claim rate;
- plan-size and feasibility behaviour for constrained personas;
- output-schema validity.

The frozen B result is a synthetic engineering baseline, not clinical validation. The AMD report must preserve that wording.

### 8.5 Result artefacts

Recommended paths:

```text
evaluation/amd/
├── benchmark.py
├── configs/
│   ├── r0_baseline.yaml
│   └── r1_optimised.yaml
└── results/
    └── <hardware-id>/
        ├── environment.json
        ├── raw_requests.jsonl
        ├── summary.json
        └── summary.csv
```

## 9. Optimisation sequence

Optimise in this order so that each change has an attributable result:

1. establish a correct FP16 or BF16 Radeon baseline;
2. cap context and generation lengths to the frozen application requirements;
3. remove duplicated prompt or retrieval context without removing required evidence;
4. evaluate a supported lower-precision or quantised representation;
5. enable supported attention, kernel, cache, graph, or compilation optimisations;
6. evaluate runtime-specific batching only if it matches the single-user local-agent scenario;
7. choose the smallest model or format that still passes behaviour-preservation gates;
8. rerun the complete quality, safety, privacy, and performance suite;
9. document rejected optimisations and their measured regressions.

Each optimisation entry must state:

- hypothesis;
- configuration change;
- hardware and software environment;
- before and after measurements;
- quality or safety effect;
- decision and rationale.

Recommended document:

```text
docs/amd_optimization.md
```

## 10. Privacy mode

`local_only` privacy mode is an application guarantee, not merely a model-location label.

Required behaviour:

- all model inference uses the local Radeon provider;
- remote model endpoints are disabled;
- prompts, user records, retrieved evidence chunks, plans, and audit payloads remain on the host;
- logs remain metadata-only and follow the existing redaction policy;
- the application does not upload benchmark inputs or outputs automatically;
- external evidence is prepared before the measured offline inference run or served from the local evidence store;
- startup rejects contradictory configuration;
- a repeatable network-egress check is documented and its result is saved.

The demo must show the selected provider, Radeon device, model, and `local_only` status without exposing sensitive configuration.

## 11. Development work packages

### AMD-1 — Provider and environment

- implement the Radeon or ROCm provider behind `LLMProvider`;
- add dependency and environment documentation;
- add provider contract, startup, failure, and integration tests;
- expose non-sensitive health metadata.

### AMD-2 — Privacy mode

- add local-only configuration and validation;
- block remote inference in local-only mode;
- add privacy-mode integration and egress tests;
- document offline evidence preparation.

### AMD-3 — Benchmarks and optimisation

- implement fixed benchmark runner;
- record environment manifest and raw results;
- benchmark candidates and select the final model and runtime;
- document measured optimisations and regressions;
- rerun frozen behaviour-preservation metrics.

### AMD-4 — Submission package

- prepare English project specification and architecture diagram;
- prepare clean setup, startup, dependency, and reproduction instructions;
- record the three-to-five-minute Radeon demo;
- prepare PPT or poster;
- fork the official repository and open the final pull request.

## 12. Required competition deliverables

According to the official Track 2 submission repository, the final package must contain:

1. **Project Specification Document**
   - application scenarios;
   - agent architecture diagram;
   - core capabilities;
   - model and local deployment plan;
   - Radeon inference-speed optimisation description.

2. **Project Source Code**
   - complete source repository;
   - README with environment configuration, startup instructions, and dependencies.

3. **Demo Video**
   - recommended length: three to five minutes;
   - actual execution on an AMD Radeon GPU;
   - command-line or GUI operation through final result;
   - visible fluidity and functional completeness.

4. **One Supplementary Item**
   - PPT or poster.

Recommended local organisation:

```text
submission/amd/
├── project_specification.md
├── project_specification.pdf
├── architecture.mmd
├── demo_script.md
├── demo_evidence/
├── poster-or-slides/
└── submission_checklist.md
```

Final materials and the submission pull request must be in English.

## 13. Submission checklist

### Eligibility and identity

- [x] Track 2 selected.
- [x] Hackathon registration accepted.
- [x] Solo participation is the current working assumption.
- [ ] Exact registered team name or no-team status checked in the private Luma record.
- [ ] Active AMD AI Developer Program membership verified for every participant.
- [ ] Current Rules and Conditions reviewed and accepted.
- [ ] Private registered identity matches the final pull-request identity.
- [ ] No personal email, access token, ticket URL, or account identifier committed publicly.

### Scope and code

- [x] `amd-track2` is the only AMD development branch.
- [x] `main` remains the canonical B product.
- [x] `docs/amd_scope.md` freezes the extension boundary.
- [ ] Radeon or ROCm provider implements the existing `LLMProvider` contract.
- [ ] Local-only privacy mode is enforced and tested.
- [ ] Existing CarePath tests pass.
- [ ] Full frozen evaluation suite passes or every regression is explicitly reported.
- [ ] Raw benchmark results and environment manifest are saved.
- [ ] Optimisation decisions are evidence-based and documented.
- [ ] Repository contains no active `ResearchRoom Verify` code, document, issue, or narrative.
- [ ] No duplicated CarePath product tree exists.

Suggested repository check:

```bash
rg -n -i 'ResearchRoom|ResearchRoom Verify' . \
  --glob '!docs/amd_scope.md' \
  --glob '!.git/**'
```

Expected result: no matches.

### Materials

- [ ] English project specification complete.
- [ ] Agent architecture diagram complete.
- [ ] Model and local deployment plan complete.
- [ ] Radeon optimisation explanation includes measured before and after results.
- [ ] Source README includes environment, dependencies, startup, privacy mode, and reproduction steps.
- [ ] Three-to-five-minute video shows an actual Radeon execution.
- [ ] PPT or poster complete.
- [ ] Limitations, non-clinical status, and synthetic-evaluation wording are visible.

### Official submission

- [ ] Fork `AMD-DEV-CONTEST/Radeon-hackathon-2026-07`.
- [ ] Add or link the required English materials according to the official repository instructions.
- [ ] Use the exact title `Track 2, <registered team or participant name>, CarePath`.
- [ ] Check every link from a logged-out browser.
- [ ] Open the pull request before 2026-08-06 23:59 UTC+8.
- [ ] Save the final pull-request URL and commit SHA in the private submission record.

## 14. Definition of done

The AMD extension is complete only when all of the following are true:

- it is demonstrably the same CarePath B product running through a Radeon-specific local provider;
- no parallel product or duplicated architecture exists;
- local-only privacy mode is enforced and evidenced;
- baseline and optimised Radeon performance are reproducibly measured;
- frozen CarePath safety, grounding, tool, personalisation, and schema behaviour are preserved or any limitation is transparently reported;
- the exact model, runtime, hardware, software, commit, and configuration are recorded;
- the required English specification, source instructions, Radeon demo, and PPT or poster are complete;
- AMD AI Developer Program membership and Rules and Conditions acceptance are verified privately;
- the official submission pull request uses the required title format and is opened before the deadline;
- `ResearchRoom Verify` remains retired and absent from active implementation and submission materials.
