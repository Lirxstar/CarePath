from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "docs" / "architecture.md"
DIAGRAMS = ROOT / "docs" / "diagrams"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_architecture_artifacts_exist() -> None:
    required = {
        ARCHITECTURE,
        DIAGRAMS / "system-architecture.mmd",
        DIAGRAMS / "agent-state-flow.mmd",
        DIAGRAMS / "trust-boundaries.mmd",
        DIAGRAMS / "deployment-boundary.mmd",
    }
    assert all(path.is_file() for path in required)


def test_every_required_module_has_an_interface_contract() -> None:
    architecture = read(ARCHITECTURE)
    required_modules = {
        "React Native / Expo",
        "FastAPI",
        "Bounded Agent Workflow",
        "Safety Triage",
        "Context Builder",
        "Tool Router",
        "Time-Series Tools",
        "Personal Context Retriever",
        "External Evidence Retriever",
        "Planner",
        "Verifier",
        "Composer",
        "ModelProvider",
        "User Persistence",
        "External Evidence Ingestion",
        "Audit Writer",
        "Operational Logger",
    }
    for module in required_modules:
        assert f"| {module} |" in architecture


def test_agent_state_flow_contains_required_states_and_bounded_loop() -> None:
    state_flow = read(DIAGRAMS / "agent-state-flow.mmd")
    required_states = {
        "Safety_Triage",
        "Context_Builder",
        "Tool_Router",
        "Personal_Context_Retriever",
        "External_Evidence_Retriever",
        "Analytics_Tools",
        "Planner",
        "Verifier",
        "Composer",
    }
    assert state_flow.startswith("stateDiagram-v2")
    assert required_states.issubset(set(state_flow.replace(":", " ").split()))
    assert "one bounded regeneration" in state_flow
    assert "risk" in state_flow.lower() and "never downgrade" in state_flow.lower()


def test_system_and_trust_diagrams_make_boundaries_explicit() -> None:
    system = read(DIAGRAMS / "system-architecture.mmd")
    trust = read(DIAGRAMS / "trust-boundaries.mmd")
    for boundary in ("TB-1", "TB-2", "TB-3", "TB-4", "TB-5"):
        assert boundary in system
        assert boundary in trust

    required_forbidden_paths = {
        "external text → policy/tool authority",
        "model endpoint ↔ persistence",
        "raw journal/prompt/secret → logs",
    }
    for forbidden_path in required_forbidden_paths:
        assert forbidden_path in trust


def test_sensitive_crossings_declare_minimization_or_scope() -> None:
    system = read(DIAGRAMS / "system-architecture.mmd")
    required_controls = {
        "authenticated + consented",
        "user-scoped",
        "selected observations only",
        "minimal personal context",
        "validated/sanitized chunks",
        "no DB credentials/access",
        "untrusted completion",
        "schema-controlled audit event",
        "status · latency · error class only",
    }
    for control in required_controls:
        assert control in system


def test_deployment_diagram_distinguishes_all_required_targets() -> None:
    deployment = read(DIAGRAMS / "deployment-boundary.mmd")
    required_targets = {
        "Local Docker Compose",
        "AWS deployment boundary",
        "Third-party cloud model provider boundary",
        "local Radeon/ROCm runtime",
        "Hosted Radeon provider boundary",
        "local_strict",
        "no silent cloud fallback",
    }
    for target in required_targets:
        assert target in deployment

    assert 'CM -. "untrusted completion" .-> LMP' in deployment
