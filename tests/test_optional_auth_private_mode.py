from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from backend.api.app.auth import AuthIdentity, AuthTokenInvalidError, carepath_account_user_id
from backend.api.app.config import Settings
from backend.api.app.main import create_app
from backend.storage.database import Base, create_database_engine, get_session
from backend.storage.models import UserProfileTable
from backend.storage.private_sessions import PrivateSessionStore


class FakeAuthVerifier:
    def verify(self, access_token: str) -> AuthIdentity:
        if access_token == "account-a":
            return AuthIdentity(subject="subject-a", email="a@example.com")
        if access_token == "account-b":
            return AuthIdentity(subject="subject-b", email="b@example.com")
        raise AuthTokenInvalidError("invalid token")


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'auth-private.db'}")
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    settings = Settings(
        environment="test",
        llm_provider="mock",
        supabase_url="https://project.supabase.co",
        supabase_publishable_key=SecretStr("sb_publishable_test"),
        private_session_ttl_minutes=15,
    )
    application = create_app(settings)
    application.state.auth_verifier = FakeAuthVerifier()
    application.dependency_overrides[get_session] = override_session
    try:
        with TestClient(application) as client:
            yield client, factory
    finally:
        application.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def profile_payload(user_id: UUID, *, synthetic: bool = False) -> dict[str, object]:
    return {
        "user_id": str(user_id),
        "age_band": "30-44",
        "preferred_language": "en",
        "timezone": "UTC",
        "health_goals": ["sleep", "physical_activity"],
        "consent_flags": {"synthetic_demo": synthetic},
    }


def json_import_payload(user_id: UUID, *, synthetic: bool = False) -> dict[str, object]:
    return {
        "source_format": "json",
        "content": {
            "profile": profile_payload(user_id, synthetic=synthetic),
            "observations": [],
            "journal_entries": [],
            "goals": [],
            "intervention_history": {
                "plans": [],
                "actions": [],
                "plan_feedback": [],
            },
        },
    }


def test_public_runtime_config_exposes_only_client_safe_auth_values(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    response = client.get("/config/public")

    assert response.status_code == 200
    assert response.json() == {
        "auth_enabled": True,
        "supabase_url": "https://project.supabase.co",
        "supabase_publishable_key": "sb_publishable_test",
        "private_mode_available": True,
        "private_session_ttl_minutes": 15,
    }


def test_private_mode_is_isolated_and_never_writes_to_persistent_database(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    first = client.post("/privacy/session").json()
    second = client.post("/privacy/session").json()
    assert first["persistent_storage"] is False
    assert first["ttl_minutes"] == 15
    assert first["session_id"] != second["session_id"]

    user_id = uuid4()
    private_headers = {"X-CarePath-Private-Session": first["session_id"]}
    assert client.post("/profiles", json=profile_payload(user_id), headers=private_headers).status_code == 201
    assert client.get(f"/profiles/{user_id}", headers=private_headers).status_code == 200

    other_headers = {"X-CarePath-Private-Session": second["session_id"]}
    assert client.get(f"/profiles/{user_id}", headers=other_headers).status_code == 404

    with factory() as session:
        assert session.get(UserProfileTable, str(user_id)) is None

    ended = client.post("/privacy/session/end", headers=private_headers)
    assert ended.status_code == 200
    assert ended.json() == {"cleared": True}
    expired = client.get(f"/profiles/{user_id}", headers=private_headers)
    assert expired.status_code == 404
    assert expired.json()["error"]["code"] == "private_session_not_found"
    assert client.post("/privacy/session/end", headers=private_headers).json() == {"cleared": False}


def test_private_session_validation_is_controlled(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    missing = client.post("/privacy/session/end")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "private_session_required"

    invalid = client.get(
        f"/profiles/{uuid4()}",
        headers={"X-CarePath-Private-Session": "not-a-uuid"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_private_session"


def test_authenticated_import_is_bound_to_stable_account_and_protected(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    submitted_user_id = uuid4()
    account_user_id = carepath_account_user_id("subject-a")

    imported = client.post(
        "/records/import",
        json=json_import_payload(submitted_user_id),
        headers={"Authorization": "Bearer account-a"},
    )
    assert imported.status_code == 200
    assert imported.json()["status"] == "success"

    with factory() as session:
        assert session.get(UserProfileTable, str(submitted_user_id)) is None
        profile = session.get(UserProfileTable, str(account_user_id))
        assert profile is not None
        assert profile.consent_flags["account_managed"] is True

    me = client.get("/auth/me", headers={"Authorization": "Bearer account-a"})
    assert me.status_code == 200
    assert me.json()["carepath_user_id"] == str(account_user_id)
    assert me.json()["email"] == "a@example.com"
    assert me.json()["profile_exists"] is True

    anonymous = client.get(f"/profiles/{account_user_id}")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "authentication_required"

    own = client.get(
        f"/profiles/{account_user_id}", headers={"Authorization": "Bearer account-a"}
    )
    assert own.status_code == 200

    other = client.get(
        f"/profiles/{account_user_id}", headers={"Authorization": "Bearer account-b"}
    )
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "user_scope_forbidden"


def test_synthetic_personas_remain_public_even_when_loaded_while_signed_in(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    synthetic_id = uuid4()
    imported = client.post(
        "/records/import",
        json=json_import_payload(synthetic_id, synthetic=True),
        headers={"Authorization": "Bearer account-a"},
    )
    assert imported.status_code == 200
    assert client.get(f"/profiles/{synthetic_id}").status_code == 200
    assert client.get(
        f"/profiles/{synthetic_id}", headers={"Authorization": "Bearer account-b"}
    ).status_code == 200


def test_signed_in_private_import_uses_account_identity_without_persistence(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_client
    account_user_id = carepath_account_user_id("subject-a")
    private = client.post("/privacy/session").json()
    headers = {
        "Authorization": "Bearer account-a",
        "X-CarePath-Private-Session": private["session_id"],
    }

    response = client.post("/records/import", json=json_import_payload(uuid4()), headers=headers)
    assert response.status_code == 200
    assert client.get(f"/profiles/{account_user_id}", headers=headers).status_code == 200

    with factory() as session:
        assert session.get(UserProfileTable, str(account_user_id)) is None

    assert client.post("/privacy/session/end", headers=headers).json() == {"cleared": True}


def test_invalid_bearer_tokens_and_header_shapes_are_rejected(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = api_client
    user_id = uuid4()

    malformed = client.get(f"/profiles/{user_id}", headers={"Authorization": "Basic abc"})
    assert malformed.status_code == 401
    assert malformed.json()["error"]["code"] == "invalid_authorization_header"

    invalid = client.get(f"/profiles/{user_id}", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_access_token"


def test_private_session_store_validates_capacity_and_evicts_oldest() -> None:
    with pytest.raises(ValueError, match="ttl_minutes"):
        PrivateSessionStore(ttl_minutes=0)
    with pytest.raises(ValueError, match="max_sessions"):
        PrivateSessionStore(max_sessions=0)

    store = PrivateSessionStore(ttl_minutes=5, max_sessions=1)
    first = store.create()
    second = store.create()
    with pytest.raises(KeyError):
        store.open(first)
    with store.open(second) as session:
        assert session is not None
    store.close_all()
