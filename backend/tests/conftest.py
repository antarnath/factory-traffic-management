"""
Shared pytest fixtures.

Tests run against an in-memory SQLite database so they don't need a real DB
server. The schema is created in-memory from the SQLAlchemy metadata on the
first request, and dropped at session teardown.
"""
import os

# Use a per-process in-memory SQLite for tests BEFORE any app module loads,
# so `app.config.settings.db_url` already has the right value.
os.environ.setdefault("DB_URL", "sqlite:///:memory:")
os.environ.setdefault("DEBUG", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings  # noqa: E402  (after env override)
from app.db import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

# Import models so SQLAlchemy registers them on Base.metadata.
import app.models  # noqa: F401, E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Yield a SQLAlchemy session bound to the test engine."""
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """TestClient with `get_db` overridden to use the test session."""

    def _override_get_db():
        try:
            yield db
        finally:
            pass  # session lifecycle owned by the `db` fixture

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()
