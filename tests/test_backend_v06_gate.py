from __future__ import annotations

import csv
import io
from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.agents import (
    CarePathWorkflow,
    ToolCall,
    VerificationDisposition,
    WorkflowState,
)
from backend.api.app import routes
from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.retrieval import DualRetriever, InMemoryRetrievalStore, RetrievalNamespace
from backend.storage.database import Base, create_database_engine, get_session

TEST_SETTINGS = Settings(environment="test", llm_provider="mock")


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'v06.db'}")
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    application = create_app(TEST_SETTINGS)
    application.dependency_overrides[get_session] = override_session
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _profile(user_id: UUID, language: str = "en") -> dict[str, object]:
    return {
        "user_id": str(user_id),
        "age_band": "30-44",
        "preferred_language": language,
        "timezone": "UTC",
        "health_goals": ["sleep"],
        "consent_flags": {"demo": True},
    }


def _sleep_csv(user_id: UUID) -> str:
    fieldnames = [
        "observation_id",
        "user_id",
        "metric_type",
        "value_numeric",
        "value_boolean",
        "unit",
        "observed_at",
        "source_type",
        "quality_flag",
        "confidence",
        "metadata",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for day_number in range(1, 15):
        writer.writerow(
            {
                "observation_id": str(uuid4()),
                "user_id": str(user_id),
                "metric_type": "sleep_duration",
                "value_numeric": "7.5" if day_number <= 7 else "6.4",
                "value_boolean": "",
                "unit": "hours",
                "observed_at": f"2026-07-{day_number:02d}T12:00:00+00:00",
                "source_type": "synthetic_wearable",
                "quality_flag": "valid",
                "confidence": "1",
                "metadata": "",
            }
        )
    return buffer.getvalue()


def _create_user(client: TestClient, *, with_observations: bool) -> UUID:
    user_id = uuid4()
    assert client.post("/profiles", json=_profile(user_id)).status_code == 201
    if with_observations:
        response = client.post(
            "/records/import",
            json={"source_format": "csv", "content": _sleep_csv(user_id)},
        )
        assert response.status_code == 200
    return user_id


def _coach(
    client: TestClient,
    user_id: UUID,
    message: str = "Help me make a realistic sleep plan for this week",
    language: str = "en",
):
    return client.post(
        "/coach/message",
        json={"user_id": str(user_id), "message": message, "language": language},
    )


def _empty_retriever() -> DualRetriever:
    return DualRetriever(
        InMemoryRetrievalStore(RetrievalNamespace.PERSONAL),
        InMemoryRetrievalStore(RetrievalNamespace.EXTERNAL),
    )


def _workflow_builder(
    *,
    tool_router=lambda state: (),
    tool_executors=None,
    retriever=None,
    planner=lambda state: {"claims": []},
    verifier=lambda state: VerificationDisposition.PASS,
    composer=lambda state: "verified",
):
    def build(**kwargs):
        del kwargs
        return CarePathWorkflow(
            context_builder=lambda state: {"safe": True},
            tool_router=tool_router,
            tool_executors=tool_executors or {},
            retriever=retriever or _empty_retriever(),
            planner=planner,
            verifier=verifier,
            composer=composer,
        )

    return build


def test_gate_01_normal_coaching_returns_all_six_structured_sections(
    api_client: TestClient,
) -> None:
    user_id = _create_user(api_client, with_observations=True)

    response = _coach(api_client, user_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["verification_disposition"] == "pass"
    structured = payload["structured_response"]
    assert structured["what_i_noticed"]
    assert structured["what_the_evidence_suggests"]
    assert len(structured["realistic_plan_for_this_week"]) == 7
    assert structured["when_to_seek_professional_help"]
    assert "sources" in structured
    assert structured["what_i_am_uncertain_about"]


def test_gate_02_data_insufficient_path_is_explicit_and_conservative(
    api_client: TestClient,
) -> None:
    user_id = _create_user(api_client, with_observations=False)

    response = _coach(api_client, user_id, "Help me build a sleep routine")

    assert response.status_code == 200
    structured = response.json()["structured_response"]
    uncertainty = " ".join(structured["what_i_am_uncertain_about"])
    assert response.json()["status"] == "completed"
    assert "limited" in uncertainty.lower() or "sleep_duration" in uncertainty
    assert len(structured["realistic_plan_for_this_week"]) == 7


def test_gate_03_empty_external_retrieval_never_creates_pseudo_citations(
    api_client: TestClient,
) -> None:
    user_id = _create_user(api_client, with_observations=True)

    response = _coach(api_client, user_id)

    assert response.status_code == 200
    structured = response.json()["structured_response"]
    external = [
        source for source in structured["sources"] if source["source_type"] == "external_guideline"
    ]
    assert external == []
    assert "No matching external guideline" in " ".join(structured["what_i_am_uncertain_about"])


def test_gate_04_high_risk_escalation_bypasses_weekly_plan(api_client: TestClient) -> None:
    user_id = _create_user(api_client, with_observations=False)

    response = _coach(api_client, user_id, "I cannot breathe")

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "urgent"
    assert payload["status"] == "blocked"
    assert payload["structured_response"]["realistic_plan_for_this_week"] == []
    assert "local emergency services" in payload["response_text"]


def test_gate_05_tool_failure_is_controlled_and_stack_free(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _create_user(api_client, with_observations=False)

    def fail_tool(arguments):
        del arguments
        raise RuntimeError("private tool stack payload")

    builder = _workflow_builder(
        tool_router=lambda state: [ToolCall(call_id="tool-1", tool_name="trend", arguments={})],
        tool_executors={"trend": fail_tool},
    )
    monkeypatch.setattr(routes, "build_runtime_workflow", builder)

    response = _coach(api_client, user_id, "Help me with sleep")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "private tool stack payload" not in response.text
    assert payload["structured_response"]["realistic_plan_for_this_week"] == []


def test_gate_06_model_timeout_is_fail_closed_and_does_not_leak_exception(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _create_user(api_client, with_observations=False)

    def timeout_planner(state: WorkflowState):
        del state
        raise TimeoutError("provider timeout with private prompt")

    monkeypatch.setattr(
        routes, "build_runtime_workflow", _workflow_builder(planner=timeout_planner)
    )

    response = _coach(api_client, user_id, "Help me with sleep")

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert "provider timeout with private prompt" not in response.text
    assert response.json()["structured_response"]["realistic_plan_for_this_week"] == []


def test_gate_07_retrieval_failure_is_controlled(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _create_user(api_client, with_observations=False)

    class FailingStore(InMemoryRetrievalStore):
        def search(self, query, *, top_k=5, user_id=None):
            del query, top_k, user_id
            raise RuntimeError("private retrieval payload")

    retriever = DualRetriever(
        FailingStore(RetrievalNamespace.PERSONAL),
        InMemoryRetrievalStore(RetrievalNamespace.EXTERNAL),
    )
    monkeypatch.setattr(
        routes,
        "build_runtime_workflow",
        _workflow_builder(retriever=retriever),
    )

    response = _coach(api_client, user_id, "Help me with sleep")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "private retrieval payload" not in response.text


def test_gate_08_verifier_second_failure_blocks_after_exactly_one_rewrite(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _create_user(api_client, with_observations=False)
    planner_calls = 0

    def planner(state: WorkflowState):
        nonlocal planner_calls
        del state
        planner_calls += 1
        return {"claims": []}

    monkeypatch.setattr(
        routes,
        "build_runtime_workflow",
        _workflow_builder(
            planner=planner,
            verifier=lambda state: VerificationDisposition.REGENERATE_ONCE,
        ),
    )

    response = _coach(api_client, user_id, "Help me with sleep")

    assert response.status_code == 200
    assert planner_calls == 2
    assert response.json()["status"] == "blocked"
    assert response.json()["verification_disposition"] == "fallback"
    assert response.json()["structured_response"]["realistic_plan_for_this_week"] == []


def test_gate_09_audit_endpoint_replays_one_interaction_in_order(api_client: TestClient) -> None:
    user_id = _create_user(api_client, with_observations=True)
    coach = _coach(api_client, user_id)
    interaction_id = coach.json()["interaction_id"]

    audit = api_client.get(f"/audit/{interaction_id}")

    assert audit.status_code == 200
    events = audit.json()["events"]
    assert [event["sequence_number"] for event in events] == list(range(1, len(events) + 1))
    event_types = [event["event_type"] for event in events]
    assert event_types[0] == "safety_decision"
    assert "verification" in event_types
    assert event_types[-1] == "response_emitted"


def test_gate_10_primary_user_story_succeeds_three_consecutive_times(
    api_client: TestClient,
) -> None:
    user_id = _create_user(api_client, with_observations=True)
    interaction_ids: set[str] = set()

    for _ in range(3):
        response = _coach(api_client, user_id)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["verification_disposition"] == "pass"
        assert len(payload["structured_response"]["realistic_plan_for_this_week"]) == 7
        interaction_ids.add(payload["interaction_id"])

    assert len(interaction_ids) == 3
