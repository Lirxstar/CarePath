from evaluation.amd.privacy_egress_check import run_check


def test_cp101_local_privacy_egress_check_passes() -> None:
    payload = run_check()

    assert payload["pass"] is True
    assert payload["mode"] == "local_strict"
    assert all(payload["checks"].values())
    observation = payload["network_observation"]
    assert observation["model_server_requests"] >= 3
    assert observation["proxy_or_redirect_trap_requests"] == 0
