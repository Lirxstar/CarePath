import json
import sys
from pathlib import Path

from backend.evaluation.privacy_egress import main, run_check


def test_privacy_egress_check_passes() -> None:
    payload = run_check()

    assert payload["pass"] is True
    assert payload["mode"] == "local_strict"
    assert payload["network_observation"]["proxy_or_redirect_trap_requests"] == 0
    assert all(payload["checks"].values())


def test_privacy_egress_cli_writes_evidence(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "privacy-egress.json"
    monkeypatch.setattr(sys, "argv", ["carepath-privacy-egress", "--output", str(output)])

    assert main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pass"] is True
    assert "privacy-egress.json" in capsys.readouterr().out
