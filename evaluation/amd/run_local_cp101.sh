#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RESULT_DIR="$ROOT_DIR/evaluation/amd/results"
LOG_DIR="$RESULT_DIR/logs"
RESULT_FILE="$RESULT_DIR/local_radeon_cp101_full.json"
SERVER_LOG="$LOG_DIR/local-vllm.log"
SERVER_PID_FILE="$LOG_DIR/local-vllm.pid"
MODEL_ID="${CAREPATH_RADEON_MODEL_ID:-Qwen/Qwen2.5-7B-Instruct}"
PORT="${CAREPATH_RADEON_PORT:-8000}"
BASE_URL="http://127.0.0.1:${PORT}"
VENV_DIR="$ROOT_DIR/.venv-cp101"
SERVER_PID=""

mkdir -p "$RESULT_DIR" "$LOG_DIR"

log() {
  printf '[CP-101] %s\n' "$*"
}

fail() {
  printf '[CP-101] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command is unavailable: $1"
}

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    log "Stopping local vLLM server (PID $SERVER_PID)"
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$SERVER_PID_FILE"
}
trap cleanup EXIT INT TERM

require_command git
require_command curl
require_command rocm-smi
require_command rocminfo

CURRENT_BRANCH="$(git branch --show-current)"
[[ "$CURRENT_BRANCH" == "amd-track2" ]] || fail "Run this command from the amd-track2 branch; current branch is ${CURRENT_BRANCH:-detached}."

if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "The repository has tracked changes. Commit or discard them before the measured run."
fi

log "Refreshing amd-track2 with a fast-forward-only pull"
git fetch origin amd-track2
git pull --ff-only origin amd-track2

VLLM_BIN="$(command -v vllm || true)"
[[ -n "$VLLM_BIN" ]] || fail "vLLM is unavailable. Use the ROCm vLLM-dev (Navi) workspace image."

RUNTIME_PYTHON="${CAREPATH_RADEON_RUNTIME_PYTHON:-}"
if [[ -z "$RUNTIME_PYTHON" ]]; then
  VLLM_SHEBANG="$(head -n 1 "$VLLM_BIN" 2>/dev/null || true)"
  if [[ "$VLLM_SHEBANG" == '#!'* ]]; then
    SHEBANG_BODY="${VLLM_SHEBANG#\#!}"
    if [[ "$SHEBANG_BODY" == '/usr/bin/env '* ]]; then
      ENV_COMMAND="${SHEBANG_BODY#/usr/bin/env }"
      ENV_COMMAND="${ENV_COMMAND%% *}"
      RUNTIME_PYTHON="$(command -v "$ENV_COMMAND" || true)"
    else
      CANDIDATE="${SHEBANG_BODY%% *}"
      if [[ -x "$CANDIDATE" ]]; then
        RUNTIME_PYTHON="$CANDIDATE"
      fi
    fi
  fi
fi
if [[ -z "$RUNTIME_PYTHON" ]]; then
  RUNTIME_PYTHON="$(command -v python3 || command -v python || true)"
fi
[[ -x "$RUNTIME_PYTHON" ]] || fail "Could not resolve the Python interpreter that owns vLLM/ROCm."

log "Checking the serving runtime and Radeon/HIP accelerator"
"$RUNTIME_PYTHON" - <<'PY'
import sys

try:
    import torch
except ImportError as exc:
    raise SystemExit("The vLLM runtime Python does not include PyTorch") from exc

print("runtime_python:", sys.version.split()[0])
print("torch:", torch.__version__)
print("hip:", torch.version.hip)
print("accelerator_available:", torch.cuda.is_available())
print("device_count:", torch.cuda.device_count())
if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
    raise SystemExit("PyTorch cannot access an AMD Radeon/HIP accelerator")
print("device_0:", torch.cuda.get_device_name(0))
PY

log "Capturing initial ROCm device status"
rocm-smi --showproductname --showdriverversion --showmeminfo vram

if curl --fail --silent --max-time 2 "$BASE_URL/v1/models" >/dev/null 2>&1; then
  fail "Port $PORT already has a model service. Stop it so this run can use a known reproducible serve command."
fi

UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" ]]; then
  log "Installing uv to create an isolated Python 3.12 CarePath client environment"
  "$RUNTIME_PYTHON" -m pip install --user 'uv>=0.8,<1'
  export PATH="$HOME/.local/bin:$PATH"
  UV_BIN="$(command -v uv || true)"
fi
[[ -n "$UV_BIN" ]] || fail "uv installation did not provide an executable."

log "Creating the isolated CarePath Python 3.12 environment"
"$UV_BIN" python install 3.12
"$UV_BIN" venv --clear --python 3.12 "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
"$UV_BIN" pip install -c requirements-dev.lock -e '.[dev]'

if [[ -d /persistent ]]; then
  export HF_HOME="${HF_HOME:-/persistent/huggingface}"
  mkdir -p "$HF_HOME"
fi

export CAREPATH_ENVIRONMENT="test"
export CAREPATH_LLM_PROVIDER="radeon_local"
export CAREPATH_PRIVACY_MODE="local_strict"
export CAREPATH_RADEON_BASE_URL="$BASE_URL"
export CAREPATH_RADEON_MODEL_ID="$MODEL_ID"
export CAREPATH_RADEON_RUNTIME="vllm_rocm"
export CAREPATH_RADEON_DEVICE="0"
export CAREPATH_RADEON_INFERENCE_DTYPE="fp16"
export CAREPATH_RADEON_REQUEST_TIMEOUT_SECONDS="180"
export CAREPATH_RADEON_MAX_NEW_TOKENS="768"
export CAREPATH_RADEON_TEMPERATURE="0"
export CAREPATH_RADEON_RUNTIME_PYTHON="$RUNTIME_PYTHON"

log "Starting Qwen2.5-7B on the loopback-only Radeon/ROCm vLLM endpoint"
"$VLLM_BIN" serve "$MODEL_ID" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --dtype half \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID="$!"
printf '%s\n' "$SERVER_PID" >"$SERVER_PID_FILE"

log "Waiting for the local model endpoint"
READY=0
for _ in $(seq 1 600); do
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    tail -n 200 "$SERVER_LOG" >&2 || true
    fail "vLLM exited before becoming ready. The log is preserved at $SERVER_LOG"
  fi
  if curl --fail --silent --max-time 2 "$BASE_URL/v1/models" >/tmp/cp101-models.json 2>/dev/null; then
    READY=1
    break
  fi
  sleep 2
done
[[ "$READY" -eq 1 ]] || {
  tail -n 200 "$SERVER_LOG" >&2 || true
  fail "vLLM did not become ready within 20 minutes."
}

log "Running the complete local privacy, environment, 48-scenario baseline and optimized evaluation"
python evaluation/amd/local_full_run.py \
  --baseline-concurrency 1 \
  --optimized-concurrency 4 \
  --warmups 1 \
  --output "$RESULT_FILE"

log "Applying the blocking CP-101 acceptance thresholds"
python evaluation/amd/validate_cp101.py "$RESULT_FILE"

log "Checking the result bundle for obvious secret material"
if grep -Eina 'api[_-]?key|bearer[[:space:]]|password|private[[:space:]]+key|/spaces/|BEGIN .*PRIVATE KEY' "$RESULT_FILE"; then
  fail "Potential secret material was detected in the result. Do not upload it before review."
fi

if [[ -d /persistent ]]; then
  BACKUP_DIR="/persistent/carepath-cp101"
  mkdir -p "$BACKUP_DIR"
  cp "$RESULT_FILE" "$BACKUP_DIR/local_radeon_cp101_full.json"
  cp "$SERVER_LOG" "$BACKUP_DIR/local-vllm.log"
  log "Saved a persistent backup under $BACKUP_DIR"
fi

log "CP-101 full local result passed. Upload only:"
log "$RESULT_FILE"
log "The model server will now stop automatically."
