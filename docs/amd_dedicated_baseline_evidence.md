# Dedicated Radeon Cloud baseline evidence

Status: measured baseline evidence, not final CP-101 acceptance.

## Captured result

Source file: `evaluation/amd/results/dedicated_radeon_benchmark.json`

- Captured at: `2026-08-06T11:29:40.061819+00:00`
- Deployment label: `dedicated_radeon_cloud`
- Provider: `radeon_cloud`
- Model: `Qwen/Qwen2.5-7B-Instruct`
- Provider health: `ok`
- Warm-up requests: 1
- Measured requests: 5
- Successful requests: 5/5
- Structured-output-valid requests: 5/5
- Requests with `diagnostic_claim=false`: 5/5
- Mean latency: 3.1071134418 seconds
- Median (p50) latency: 3.1752372500 seconds
- Observed p95 latency: 3.6598550000 seconds
- Evidence file SHA-256: `aff9c7f30286734a2d30e9fa542b68704943e413187220b541bb09068951cf5f`

The evidence file contains no API key, bearer token, endpoint URL, password, or other obvious secret field.

## What this evidence supports

This run supports the claim that CarePath successfully called a dedicated AMD-hosted OpenAI-compatible endpoint, received five successful structured responses from `Qwen/Qwen2.5-7B-Instruct`, and preserved the tested non-diagnostic schema field.

## What this evidence does not support

This file does not by itself prove:

- local execution on the end user's device;
- `local_strict` privacy or network-egress blocking;
- exact GPU identity, ROCm version, framework build, container digest, or CarePath commit;
- TTFT, output-token throughput, peak VRAM, power, or GPU utilisation;
- an unoptimised-versus-optimised comparison;
- completion of the frozen 48x4 behaviour evaluation on the measured provider;
- full CP-101 acceptance.

Those claims remain pending separate environment attestation, local-provider evidence, fixed-workload evaluation, and optimisation measurements.
