from __future__ import annotations

from _thread import LockType
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.storage import models as _storage_models  # noqa: F401

from .database import Base


class _DBAPICursor(Protocol):
    def execute(self, statement: str) -> object: ...

    def close(self) -> None: ...


class _DBAPIConnection(Protocol):
    def cursor(self) -> _DBAPICursor: ...


@dataclass
class _PrivateSessionEntry:
    engine: Engine
    session_factory: sessionmaker[Session]
    expires_at: datetime
    last_accessed_at: datetime
    operation_lock: LockType = field(default_factory=Lock)


class PrivateSessionStore:
    """Keep private-mode CarePath data only in process memory."""

    def __init__(self, *, ttl_minutes: int = 60, max_sessions: int = 128) -> None:
        if ttl_minutes <= 0:
            raise ValueError("ttl_minutes must be positive")
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_sessions = max_sessions
        self._entries: dict[UUID, _PrivateSessionEntry] = {}
        self._lock = RLock()

    @property
    def ttl_minutes(self) -> int:
        return int(self._ttl.total_seconds() // 60)

    def create(self) -> UUID:
        with self._lock:
            now = datetime.now(UTC)
            self._prune_expired_locked(now)
            while len(self._entries) >= self._max_sessions:
                self._evict_oldest_locked()

            session_id = uuid4()
            engine = self._create_memory_engine()
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
            self._entries[session_id] = _PrivateSessionEntry(
                engine=engine,
                session_factory=factory,
                expires_at=now + self._ttl,
                last_accessed_at=now,
            )
            return session_id

    @contextmanager
    def session(self, session_id: UUID) -> Generator[Session, None, None]:
        """Open one serialized database operation for a private workspace."""

        with self._lock:
            now = datetime.now(UTC)
            self._prune_expired_locked(now)
            entry = self._entries.get(session_id)
            if entry is None:
                raise KeyError(session_id)
            entry.last_accessed_at = now
            entry.expires_at = now + self._ttl
            # StaticPool intentionally keeps one in-memory SQLite connection. SQLite cannot
            # safely execute multiple transactions on that connection concurrently, so acquire
            # the per-workspace lock before releasing the registry lock. FastAPI may enter and
            # exit a synchronous generator dependency on different worker threads, so this must
            # be a primitive Lock rather than a thread-owned RLock.
            entry.operation_lock.acquire()

        try:
            with entry.session_factory() as scoped_session:
                yield scoped_session
        finally:
            entry.operation_lock.release()

    def close(self, session_id: UUID) -> bool:
        with self._lock:
            entry = self._entries.pop(session_id, None)
            if entry is None:
                return False
            entry.operation_lock.acquire()
        try:
            entry.engine.dispose()
        finally:
            entry.operation_lock.release()
        return True

    def close_all(self) -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
            for entry in entries:
                entry.operation_lock.acquire()
        try:
            for entry in entries:
                entry.engine.dispose()
        finally:
            for entry in reversed(entries):
                entry.operation_lock.release()

    def _prune_expired_locked(self, now: datetime) -> None:
        expired = [
            session_id for session_id, entry in self._entries.items() if entry.expires_at <= now
        ]
        for session_id in expired:
            entry = self._entries.pop(session_id)
            entry.operation_lock.acquire()
            try:
                entry.engine.dispose()
            finally:
                entry.operation_lock.release()

    def _evict_oldest_locked(self) -> None:
        if not self._entries:
            return
        session_id = min(
            self._entries,
            key=lambda item: self._entries[item].last_accessed_at,
        )
        entry = self._entries.pop(session_id)
        entry.operation_lock.acquire()
        try:
            entry.engine.dispose()
        finally:
            entry.operation_lock.release()

    @staticmethod
    def _create_memory_engine() -> Engine:
        engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(
            dbapi_connection: _DBAPIConnection,
            _: object,
        ) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

        return engine
