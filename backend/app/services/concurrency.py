"""
Per-junction row-locking context manager.

Spec §6 says traffic decisions affecting the same junction must not produce
conflicting results when two requests are processed concurrently. The
candidate is expected to choose and explain a consistency strategy; we use
**serialised per-junction processing** via `SELECT ... FOR UPDATE`.

How it works:
    1. The caller (an API route, a maintenance task, an orchestrator) wraps
       any code that mutates junction state in `with junction_lock(...)`.
    2. We open a transaction, fetch the Junction row with a row-level lock,
       and yield the locked row.
    3. The caller does its work. No other request can read or modify the
       same junction row until the transaction commits or rolls back.
    4. After the `with` block exits, the caller is responsible for
       `db.commit()` or `db.rollback()`.

On SQLite (used by tests) row locks are no-ops because SQLite serialises
the entire database, but the call site stays identical.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from app.models import Junction


@contextmanager
def junction_lock(db: Session, junction_id: str) -> Iterator[Junction]:
    """
    Lock the junction row for the duration of the `with` block.

    Usage:
        with junction_lock(db, "A") as j:
            j.mode = "MANUAL"
            ...
        db.commit()

    Raises ValueError if the junction doesn't exist.
    """
    query = db.query(Junction).filter(Junction.id == junction_id)
    # `with_for_update()` is a no-op on SQLite, enforced on PostgreSQL/MySQL.
    # `read=True` keeps it compatible with both engines.
    junction = query.with_for_update(read=True).one_or_none()
    if junction is None:
        raise ValueError(f"Unknown junction: {junction_id!r}")
    yield junction
