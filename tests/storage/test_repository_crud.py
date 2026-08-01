from backend.repositories.crud import CRUDRepository
from backend.storage.models import UserProfileTable


def build_user(user_id: str) -> UserProfileTable:
    return UserProfileTable(
        user_id=user_id,
        age_band="18-29",
        preferred_language="en",
        timezone="Asia/Tokyo",
        health_goals=[],
        consent_flags={},
    )


def test_repository_create_and_get(database_session) -> None:
    repository = CRUDRepository(database_session)
    user = build_user("user-test")

    repository.create(user)
    database_session.commit()

    loaded = repository.get(UserProfileTable, "user-test")

    assert loaded is not None
    assert loaded.user_id == "user-test"


def test_repository_delete(database_session) -> None:
    repository = CRUDRepository(database_session)
    user = build_user("delete-user")

    repository.create(user)
    repository.delete(user)

    assert repository.get(UserProfileTable, "delete-user") is None


def test_repository_update(database_session) -> None:
    repository = CRUDRepository(database_session)
    user = build_user("update-user")

    repository.create(user)
    user.timezone = "UTC"
    updated = repository.update(user)

    assert updated.timezone == "UTC"
    assert repository.get(UserProfileTable, "update-user") is not None
