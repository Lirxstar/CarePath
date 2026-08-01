from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.storage import Base
from backend.storage.database import create_database_engine


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    session = session_factory()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
