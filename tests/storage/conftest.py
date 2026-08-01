from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.storage.database import Base, create_database_engine


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, class_=Session, expire_on_commit=False)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()
        engine.dispose()
