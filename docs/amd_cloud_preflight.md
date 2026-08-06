# AMD Radeon Cloud Preflight

This optional preflight validates CarePath's provider contract and structured-output behavior against the official AMD Radeon Cloud OpenAI-compatible API without consuming Radeon Cloud GPU credits.

It is not the Track 2 local-inference result. It does not satisfy CP-101 requirements for local-only privacy, exact ROCm hardware, VRAM, throughput, egress, or optimisation evidence.

## Fixed public configuration

```text
Base URL: https://developer.amd.com.cn/radeon/api/v1
Model: DeepSeek-V4-Flash
Provider: radeon_cloud
Privacy mode: standard_demo
```

Only synthetic CarePath scenarios may be sent through this remote endpoint.

## Security rules

- Never commit the API key.
- Never paste the API key into an issue, pull request, screenshot, log, or chat.
- Keep `CAREPATH_PRIVACY_MODE=standard_demo`; startup must reject `radeon_cloud` under `local_strict`.
- Do not send personal health records or private journal content.
- Do not describe remote results as local Radeon execution.

## Configure an ignored environment file

From the repository root on `amd-track2`:

```bash
cp .env.example .env.amd-cloud
cat >> .env.amd-cloud <<'EOF'
CAREPATH_ENVIRONMENT=development
CAREPATH_LLM_PROVIDER=radeon_cloud
CAREPATH_PRIVACY_MODE=standard_demo
CAREPATH_RADEON_CLOUD_BASE_URL=https://developer.amd.com.cn/radeon/api/v1
CAREPATH_RADEON_CLOUD_MODEL_ID=DeepSeek-V4-Flash
CAREPATH_RADEON_CLOUD_API_KEY=PASTE_THE_PRIVATE_KEY_HERE
CAREPATH_RADEON_CLOUD_REQUEST_TIMEOUT_SECONDS=120
CAREPATH_RADEON_CLOUD_MAX_NEW_TOKENS=512
CAREPATH_RADEON_CLOUD_TEMPERATURE=0
EOF
export CAREPATH_ENV_FILE="$PWD/.env.amd-cloud"
git check-ignore -v .env.amd-cloud
```

Do not continue unless `git check-ignore` reports that the file is ignored.

## Run a direct API check

Use the key from the environment file rather than writing it into shell history:

```bash
set -a
source .env.amd-cloud
set +a
curl --fail --silent \
  "$CAREPATH_RADEON_CLOUD_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $CAREPATH_RADEON_CLOUD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "DeepSeek-V4-Flash",
    "messages": [
      {
        "role": "user",
        "content": "Reply with exactly: Radeon Cloud connected"
      }
    ],
    "temperature": 0,
    "max_tokens": 32,
    "stream": false
  }' | python -m json.tool
```

## Run the CarePath structured smoke test

```bash
python evaluation/amd/cloud_smoke_test.py \
  --output evaluation/amd/results/cloud_provider_smoke.json
python -m json.tool evaluation/amd/results/cloud_provider_smoke.json
```

The output must:

- identify `radeon_cloud` and `DeepSeek-V4-Flash`;
- contain a valid JSON object in `result`;
- keep `diagnostic_claim` false;
- contain no API key, account identifier, or private data.

## Start the API

```bash
python -m uvicorn backend.api.app.main:app \
  --host 127.0.0.1 \
  --port 8081 \
  --no-access-log
```

In another terminal:

```bash
curl --fail --silent http://127.0.0.1:8081/health | python -m json.tool
```

The provider must report `local: false`. If `CAREPATH_PRIVACY_MODE=local_strict` is selected, startup must fail rather than silently sending requests remotely.

## Cleanup

```bash
unset CAREPATH_ENV_FILE
unset CAREPATH_RADEON_CLOUD_API_KEY
rm -f .env.amd-cloud
```

Review `evaluation/amd/results/cloud_provider_smoke.json` before committing it. The file may be retained as remote preflight evidence, but it must remain clearly separated from local Radeon benchmark results.
