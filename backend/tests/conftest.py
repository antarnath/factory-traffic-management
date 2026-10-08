"""
Shared pytest fixtures.

Tests run against a file-based SQLite database (a temp file, scoped to
the test session) so we don't need a real DB server. File-based SQLite
also lets multiple connections share the same database — in-memory
`:memory:` would create a fresh DB per connection.

The conftest REPLACES `app.db.engine` and `app.db.SessionLocal` with
test versions so the FastAPI dependency `get_db` and the production
`SessionLocal` both use the same engine.
"""
import os

# Default to file-based SQLite for the test session BEFORE any app
# module loads.
os.environ.setdefault("DB_URL", "sqlite:///./_test_factory_traffic.db")
os.environ.setdefault("DEBUG", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as app_db  # noqa: E402  (must be after env override)
from app.config import settings  # noqa: E402
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
    # Replace the production engine so the app's get_db uses ours.
    app_db.engine = eng
    app_db.SessionLocal = sessionmaker(
        bind=eng, autoflush=False, autocommit=False,
        expire_on_commit=False, future=True,
    )
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Yield a SQLAlchemy session bound to the test engine."""
    session = app_db.SessionLocal()
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


@pytest.fixture(autouse=True)
def _clean_tables(engine):
    """Wipe data between tests for isolation."""
    yield
    with engine.begin() as conn:
        for table in ("audit_event", "queue_entry", "pending_command",
                      "signal", "junction_config", "junction"):
            conn.exec_driver_sql(f"DELETE FROM {table}")
