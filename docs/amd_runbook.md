# AMD Radeon Runtime Runbook

This runbook covers the only CP-101 work that requires access to a real AMD Radeon/ROCm machine. The CarePath provider, configuration validation, structured-output client, unit tests, smoke script, benchmark runner, and environment-capture script are version controlled. The operator must supply the hardware session and execute the commands below.

## 1. Security and scope rules

- Work on `amd-track2` or a branch based on it.
- Use only synthetic CarePath scenarios.
- Keep model inference on a loopback endpoint such as `127.0.0.1` when claiming `local_strict` privacy mode.
- Do not use the shared free model API or a public dedicated endpoint as evidence for local-only inference.
- Do not commit API keys, cloud tokens, SSH private keys, personal paths, hostnames, GPU UUIDs, or model-access credentials.
- Review every generated JSON evidence file before committing it.

## 2. Start a Radeon Cloud notebook

1. Sign in to Radeon Cloud.
2. Create a template with persistent storage if the files must survive instance destruction.
3. Launch the template and open its JupyterLab terminal.
4. Prefer the organiser-provided image that already contains the compatible ROCm and vLLM stack. Do not replace its driver stack without a documented reason.
5. Destroy the instance after saving the required evidence because an active instance consumes credits.

SSH is optional. The JupyterLab terminal is sufficient for the complete run.

## 3. Check out CarePath

```bash
git clone --branch amd-track2 https://github.com/Lirxstar/CarePath.git
cd CarePath
git status --short --branch
```

The expected branch is `amd-track2` and the working tree should be clean.

## 4. Inspect the AMD environment before installing anything

```bash
rocm-smi --showproductname --showdriverversion --showmeminfo vram
rocminfo | grep -E 'Name:|Marketing Name:|Device Type:|Compute Unit:' | head -n 80
python --version
python - <<'PY'
try:
    import torch
except ImportError:
    print("torch: not installed")
else:
    print("torch:", torch.__version__)
    print("hip:", torch.version.hip)
    print("accelerator available:", torch.cuda.is_available())
    print("device count:", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("device 0:", torch.cuda.get_device_name(0))
PY
```

Do not proceed if the GPU is absent from both `rocm-smi` and the framework runtime. Save the terminal output privately for troubleshooting.

## 5. Prepare the CarePath Python environment

Use a separate environment for CarePath so its dependencies do not alter the organiser's model-serving environment.

```bash
python3 -m venv .venv-carepath
source .venv-carepath/bin/activate
python -m pip install --upgrade pip
python -m pip install -c requirements-dev.lock -e '.[dev]'
python -m pip check
```

Run the CPU-safe validation suite before using the GPU:

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest tests/test_radeon_provider.py tests/test_backend_foundation.py
```

## 6. Start a local vLLM ROCm server

Use the vLLM installation already supplied by the Radeon image when available:

```bash
vllm --version
```

If it is absent, use the current vLLM ROCm installation method compatible with the image's Python and ROCm versions. Do not mix an arbitrary wheel with an incompatible ROCm driver.

Start with the primary candidate when VRAM is sufficient:

```bash
export MODEL_ID='Qwen/Qwen2.5-7B-Instruct'
mkdir -p evaluation/amd/results/logs
nohup vllm serve "$MODEL_ID" \
  --host 127.0.0.1 \
  --port 8000 \
  --dtype half \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  > evaluation/amd/results/logs/vllm.log 2>&1 &
echo $! > evaluation/amd/results/logs/vllm.pid
```

If the 7B model does not fit, record the failure and use a smaller approved candidate for initial integration. Do not silently change the model in reported results.

Check startup:

```bash
for attempt in $(seq 1 120); do
  if curl --fail --silent http://127.0.0.1:8000/v1/models >/tmp/models.json; then
    cat /tmp/models.json
    break
  fi
  sleep 2
done

tail -n 100 evaluation/amd/results/logs/vllm.log
```

The endpoint must remain loopback-only for `local_strict` evidence.

### llama.cpp alternative

Use this only when the selected Radeon environment and model format support the AMD ROCm/HIP build. Start `llama-server` on `127.0.0.1`, set `CAREPATH_RADEON_RUNTIME=llama_cpp_rocm`, and use the exact model alias reported by `/v1/models`.

## 7. Configure CarePath local-only inference

Create an untracked environment file:

```bash
cp .env.example .env.amd
cat >> .env.amd <<EOF
CAREPATH_ENVIRONMENT=development
CAREPATH_LLM_PROVIDER=radeon_local
CAREPATH_PRIVACY_MODE=local_strict
CAREPATH_RADEON_BASE_URL=http://127.0.0.1:8000
CAREPATH_RADEON_MODEL_ID=$MODEL_ID
CAREPATH_RADEON_RUNTIME=vllm_rocm
CAREPATH_RADEON_DEVICE=0
CAREPATH_RADEON_INFERENCE_DTYPE=fp16
CAREPATH_RADEON_REQUEST_TIMEOUT_SECONDS=120
CAREPATH_RADEON_MAX_NEW_TOKENS=512
CAREPATH_RADEON_TEMPERATURE=0
EOF
export CAREPATH_ENV_FILE="$PWD/.env.amd"
```

Confirm the file is ignored:

```bash
git check-ignore -v .env.amd
```

Do not continue if Git does not report an ignore rule.

## 8. Run provider health and structured smoke tests

```bash
curl --fail --silent http://127.0.0.1:8000/v1/models | python -m json.tool
python evaluation/amd/smoke_test.py \
  --output evaluation/amd/results/provider_smoke.json
cat evaluation/amd/results/provider_smoke.json
```

Required result:

- provider health is `ok`;
- provider is `radeon_local`;
- runtime is `vllm_rocm` or the explicitly selected alternative;
- structured output is valid JSON;
- the scenario remains non-diagnostic;
- the request is served by the loopback runtime.

## 9. Start CarePath and verify the API health endpoint

```bash
python -m uvicorn backend.api.app.main:app \
  --host 127.0.0.1 \
  --port 8081 \
  --no-access-log \
  > evaluation/amd/results/logs/carepath-api.log 2>&1 &
echo $! > evaluation/amd/results/logs/carepath-api.pid

for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8081/health; then
    break
  fi
  sleep 1
done
```

The health response must identify the local Radeon provider and must not contain credentials or personal paths.

## 10. Capture reproducible evidence

```bash
python evaluation/amd/capture_environment.py \
  --output evaluation/amd/results/environment.json
python evaluation/amd/benchmark_provider.py \
  --warmups 3 \
  --repetitions 5 \
  --output evaluation/amd/results/provider_benchmark.json
```

Inspect before committing:

```bash
python -m json.tool evaluation/amd/results/environment.json >/dev/null
python -m json.tool evaluation/amd/results/provider_smoke.json >/dev/null
python -m json.tool evaluation/amd/results/provider_benchmark.json >/dev/null
rg -n -i 'token|api[_-]?key|password|private|ssh-rsa|BEGIN .*PRIVATE KEY' \
  evaluation/amd/results || true
```

Remove secrets or machine identifiers if any appear. Do not edit measured values to improve results.

## 11. Stop processes and destroy the instance

```bash
kill "$(cat evaluation/amd/results/logs/carepath-api.pid)" 2>/dev/null || true
kill "$(cat evaluation/amd/results/logs/vllm.pid)" 2>/dev/null || true
```

After copying or committing the reviewed evidence, destroy the Radeon Cloud instance to stop credit consumption.

## 12. Evidence that must be returned to the repository

At minimum:

```text
evaluation/amd/results/
├── environment.json
├── provider_smoke.json
├── provider_benchmark.json
└── logs/
    ├── carepath-api.log
    └── vllm.log
```

Logs must be sanitized and may be reduced to the relevant startup, device, model, and error sections. Never commit the `.env.amd` file.

## 13. Completion boundary

The code-side provider task is complete when CI passes. CP-101 itself remains open until a real Radeon run produces reviewed environment, smoke, benchmark, privacy, and full behaviour-preservation evidence. A mock, CPU, shared remote API, or public dedicated API cannot satisfy that hardware acceptance boundary.
