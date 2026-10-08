"""
Desired-vs-actual reconciliation.

The spec says (§8): "If the actual signal state differs from the desired
state for longer than the controller timeout, the system should mark the
controller as DEGRADED and stop sending new commands until the discrepancy
is resolved."

This module is a small helper called from the maintenance tick. It looks at
each Signal row, compares `desired_state` to `actual_state`, and if the
discrepancy has persisted too long, marks the junction as DEGRADED.

We keep the "too long" threshold the same as the controller ACK timeout so
that this check is a backstop, not a parallel timer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Junction, Signal
from app.services.concurrency import junction_lock
from app.services.orchestrator import _audit, _now
from app.services.timeouts import DEFAULT_COMMAND_TIMEOUT_SEC


def _now() -> datetime:
    return datetime.now(timezone.utc)


def reconcile_junction(db: Session, junction_id: str,
                       max_drift_sec: int = DEFAULT_COMMAND_TIMEOUT_SEC
                       ) -> bool:
    """
    Check one junction's signals for desired/actual drift. If any signal
    has been out of sync for more than `max_drift_sec`, mark the junction
    DEGRADED. Returns True if a state change happened.
    """
    with junction_lock(db, junction_id) as junction:
        if junction is None:
            return False
        if junction.controller_status in ("OFFLINE", "DEGRADED"):
            return False  # already known to be in trouble

        now = _now()
        drifted = False
        for sig in junction.signals:
            if sig.desired_state == sig.actual_state:
                continue
            # How long has it been drifting?
            # We don't track per-signal drift timestamps, so we use the
            # last_changed_at as a conservative proxy: the discrepancy
            # has existed at least since the desired_state was last set.
            since = sig.last_changed_at
            if since is None:
                continue
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            if (now - since).total_seconds() >= max_drift_sec:
                drifted = True
                break

        if drifted:
            junction.controller_status = "DEGRADED"
            junction.mode = "DEGRADED"
            _audit(db, "DESIRED_ACTUAL_DRIFT_DETECTED", junction, "",
                   {"max_drift_sec": max_drift_sec})
            return True
        return False


def reconcile_all(db: Session,
                  max_drift_sec: int = DEFAULT_COMMAND_TIMEOUT_SEC
                  ) -> list[str]:
    """Run reconcile_junction for every junction. Returns IDs that changed."""
    changed: list[str] = []
    for j in db.query(Junction).all():
        if reconcile_junction(db, j.id, max_drift_sec):
            changed.append(j.id)
    return changed
