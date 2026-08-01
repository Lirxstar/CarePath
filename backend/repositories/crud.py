from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

Entity = TypeVar("Entity")
Model = TypeVar("Model")


class CRUDRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, entity: Entity) -> Entity:
        self.session.add(entity)
        self.session.flush()
        return entity

    def get(self, model: type[Model], identifier: Any) -> Model | None:
        return self.session.get(model, identifier)

    def update(self, entity: Entity) -> Entity:
        merged = self.session.merge(entity)
        self.session.flush()
        return merged

    def delete(self, entity: Entity) -> None:
        self.session.delete(entity)
        self.session.flush()

    def list_all(self, model: type[Model]) -> list[Model]:
        return list(self.session.scalars(select(model)).all())
