"""
SQLAlchemy 2.0 engine, session, and DeclarativeBase.

`get_db` is the FastAPI dependency that yields a per-request session
and guarantees it is closed afterwards.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Single declarative base used by every model in `app.models`."""


def _build_engine() -> Engine:
    url = settings.db_url
    connect_args: dict = {}

    # SQLite needs a special flag to allow the same connection to be used
    # across threads (FastAPI runs request handlers in a thread pool).
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
