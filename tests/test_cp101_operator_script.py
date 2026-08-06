import subprocess
from pathlib import Path

SCRIPT = Path("evaluation/amd/run_local_cp101.sh")


def test_cp101_operator_script_has_valid_bash_syntax() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr


def test_cp101_operator_script_preserves_local_and_measured_boundaries() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "--host 127.0.0.1" in content
    assert "http://127.0.0.1:" in content
    assert "0.0.0.0" not in content
    assert 'CAREPATH_PRIVACY_MODE="local_strict"' in content
    assert 'CAREPATH_LLM_PROVIDER="radeon_local"' in content
    assert "CAREPATH_RADEON_RUNTIME_PYTHON" in content
    assert "local_full_run.py" in content
    assert "validate_cp101.py" in content
    assert "--baseline-concurrency 1" in content
    assert "--optimized-concurrency 4" in content
    assert "local_radeon_cp101_full.json" in content
    assert "api[_-]?key" in content


def test_cp101_operator_script_requires_the_supported_branch_and_runtime() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert 'CURRENT_BRANCH="$(git branch --show-current)"' in content
    assert '"$CURRENT_BRANCH" == "amd-track2"' in content
    assert "git pull --ff-only origin amd-track2" in content
    assert "ROCm vLLM-dev (Navi)" in content
    assert '"$VLLM_BIN" serve "$MODEL_ID"' in content
    assert '"$RUNTIME_PYTHON" -m pip install --user' in content
    assert '"$UV_BIN" python install 3.12' in content
