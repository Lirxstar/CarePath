from typing import Any, TypeVar

from sqlalchemy.orm import Session

from backend.repositories.crud import CRUDRepository

Entity = TypeVar("Entity")
Model = TypeVar("Model")


class StorageService:
    def __init__(self, session: Session) -> None:
        self.repository = CRUDRepository(session)

    def create(self, entity: Entity) -> Entity:
        return self.repository.create(entity)

    def get(self, model: type[Model], identifier: Any) -> Model | None:
        return self.repository.get(model, identifier)

    def update(self, entity: Entity) -> Entity:
        return self.repository.update(entity)

    def delete(self, entity: Entity) -> None:
        self.repository.delete(entity)

    def list_all(self, model: type[Model]) -> list[Model]:
        return self.repository.list_all(model)
