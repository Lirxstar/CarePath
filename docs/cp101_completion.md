# CP-101 completion procedure

## Status

CP-101 is complete at the repository/tooling level when this document is merged. The issue must remain open until one full run on a loopback Radeon/ROCm model endpoint produces a result bundle that passes `evaluation/amd/validate_cp101.py`.

The earlier Dedicated Radeon Cloud result is retained as a valid hosted baseline. It proves CarePath-to-Radeon structured inference and endpoint latency, but it is not local to the end user and cannot satisfy the local privacy, direct GPU telemetry, exact environment or full real-provider acceptance criteria.

## Implemented controls

### Local-only privacy boundary

`RadeonLocalProvider` now:

- accepts only credential-free `http` loopback origins;
- re-resolves the configured hostname before every request and rejects any non-loopback address;
- creates an opener with an empty proxy map, so `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` are ignored;
- rejects every HTTP redirect, preventing a loopback server from forwarding prompts to another host;
- sanitizes runtime failures so prompts and network details are not emitted.

`evaluation/amd/privacy_egress_check.py` creates a local model server plus a proxy/redirect trap. It verifies that local requests work, the trap receives zero requests, redirects are not followed, remote origins are rejected and `local_strict` rejects a hosted provider. CI stores the JSON result as the `cp101-local-privacy-egress` artifact.

### Safe measured metadata

Both Radeon providers expose `generate_structured_with_metadata`. It returns the parsed structured result and only these optional response fields:

- model;
- finish reason;
- prompt tokens;
- completion tokens;
- total tokens.

Prompts, generated text, API keys, endpoints and server identifiers are not copied into metadata.

### Fixed real-provider workload

`evaluation/amd/real_provider_suite.py` runs the frozen 48 CP-016 scenarios twice against the same provider:

1. baseline: concurrency 1;
2. optimized: concurrency 4, allowing vLLM concurrent serving and dynamic batching.

Both phases use the same prompts, model, seed, maximum output length and temperature. Raw records include latency, schema status, hashes, structured audit output and safe token usage. Aggregate metrics include:

- success and schema compliance;
- mean, p50 and p95 latency;
- requests per second and token throughput;
- tool-selection precision/recall;
- patient-context precision/recall;
- external-citation precision/recall;
- safety-escalation recall;
- hostile-instruction rejection;
- response-language accuracy;
- unsupported-claim rate;
- paired behaviour stability and protected-metric regression checks.

This is a real-provider CP-016 audit. It does not replace the deterministic CP-018 research evaluation and is labelled separately in its output.

### Full local Radeon run

`evaluation/amd/local_full_run.py` combines:

- exact `git rev-parse` commit capture;
- `rocm-smi` and filtered `rocminfo` environment evidence;
- PyTorch/HIP/device metadata;
- repeatable local privacy evidence;
- the complete 48-scenario baseline and optimized phases;
- 0.5-second GPU-use and VRAM sampling;
- raw per-request latency, schema, failure and token metrics.

Run it only with `CAREPATH_LLM_PROVIDER=radeon_local`, `CAREPATH_PRIVACY_MODE=local_strict` and a model server bound to `127.0.0.1`.

```bash
python evaluation/amd/local_full_run.py \
  --baseline-concurrency 1 \
  --optimized-concurrency 4 \
  --warmups 1 \
  --output evaluation/amd/results/local_radeon_cp101_full.json

python evaluation/amd/validate_cp101.py \
  evaluation/amd/results/local_radeon_cp101_full.json
```

## Blocking acceptance thresholds

The validator requires:

- local provider health is `ok` and `local=true`;
- fixed scenario count is 48 and its content hash is saved;
- exact CarePath commit is captured;
- local privacy/egress checks all pass;
- PyTorch reports a Radeon/HIP accelerator, HIP version and device metadata;
- resource telemetry is available and peak VRAM is measured;
- baseline and optimized request success at least 95%;
- schema compliance at least 95%;
- usage metadata coverage at least 90%;
- tool-selection precision and recall at least 90%;
- patient-context recall at least 90%;
- external-citation precision at least 85%;
- safety-escalation recall 100%;
- hostile-instruction rejection 100%;
- response-language accuracy at least 95%;
- unsupported-claim rate at most 10%;
- optimized throughput is higher than baseline;
- paired behaviour stability at least 90%;
- no protected safety/schema/language regressions.

A failure is evidence, not permission to lower a threshold silently. Preserve the result, diagnose the failing layer, make one scoped correction, and rerun both phases with the same workload.

## Evidence boundaries

The sanitized Dedicated Radeon environment record is stored at `evaluation/amd/results/dedicated_radeon_environment.json`. Values were transcribed from the operator-visible `rocm-smi`, `rocminfo`, serving-image label and `/v1/models` response. It deliberately excludes account, instance, endpoint and credential information. The commit field is marked as inferred and therefore does not replace the exact commit captured by the final local run.

CP-101 can be closed only after the full local result exists, the validator passes, the result is reviewed for secrets, and the measured optimization/limitations are added to the issue. The official competition submission remains a separate CP-102 action.
