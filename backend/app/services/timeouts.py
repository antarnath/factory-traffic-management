"""
Time-based maintenance: manual-override expiry and ACK timeouts.

This module is the workhorse behind the `POST /api/maintenance/tick` endpoint
and the background scheduler. It is intentionally written as a list of small
"check and act" functions rather than a monolithic cron, so each check can be
unit-tested and re-run independently.

All functions are idempotent — running them twice in a row has the same effect
as running them once.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Junction, PendingCommand
from app.services.concurrency import junction_lock
from app.services.orchestrator import _audit, _now, step_junction


# Default: a command is considered "timed out" if no ACK arrives in 5s.
# Real hardware is slower; tests want this short.
DEFAULT_COMMAND_TIMEOUT_SEC = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def expire_manual_overrides(db: Session) -> list[str]:
    """
    For every junction currently in MANUAL mode whose `manual_override_until`
    is in the past, return it to AUTOMATIC. Returns the list of junction IDs
    that were reset (useful for tests and audit summaries).
    """
    now = _now()
    expired: list[str] = []
    rows = (db.query(Junction)
              .filter(Junction.mode == "MANUAL",
                      Junction.manual_override_until.isnot(None),
                      Junction.manual_override_until <= now)
              .all())
    for j in rows:
        with junction_lock(db, j.id) as junction:
            # Re-check inside the lock to avoid races.
            if (junction.mode == "MANUAL"
                    and junction.manual_override_until
                    and junction.manual_override_until <= _now()):
                junction.mode = "AUTOMATIC"
                junction.manual_override_dir = ""
                junction.manual_override_until = None
                _audit(db, "MANUAL_OVERRIDE_EXPIRED", junction, "")
                expired.append(junction.id)
                # Re-run the cycle so a sensible direction is picked.
                step_junction(db, junction.id)
    return expired


def timeout_stale_commands(db: Session,
                           timeout_sec: int = DEFAULT_COMMAND_TIMEOUT_SEC
                           ) -> list[str]:
    """
    For every PENDING/SENT command that has been waiting for an ACK longer
    than `timeout_sec`, mark it TIMEOUT and bump the junction into DEGRADED.
    Returns the list of command_ids that were timed out.
    """
    now = _now()
    cutoff = now.timestamp() - timeout_sec
    timed_out: list[str] = []

    # Pre-fetch candidates WITHOUT a lock; we'll re-check inside the
    # per-junction lock.
    candidates = (db.query(PendingCommand)
                    .filter(PendingCommand.status.in_(["PENDING", "SENT"]))
                    .all())
    for cmd in candidates:
        sent_at = cmd.sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if sent_at.timestamp() > cutoff:
            continue  # not stale yet

        with junction_lock(db, cmd.junction_id) as junction:
            # Re-fetch the command inside the lock to avoid double-timing-out.
            fresh = (db.query(PendingCommand)
                       .filter(PendingCommand.command_id == cmd.command_id)
                       .one_or_none())
            if fresh is None or fresh.status not in ("PENDING", "SENT"):
                continue
            fresh.status = "TIMEOUT"
            junction.controller_status = "DEGRADED"
            _audit(db, "CONTROLLER_TIMEOUT", junction, cmd.direction,
                   {"command_id": cmd.command_id})
            timed_out.append(cmd.command_id)

    return timed_out


def run_all_maintenance(db: Session,
                        timeout_sec: int = DEFAULT_COMMAND_TIMEOUT_SEC
                        ) -> dict:
    """
    One maintenance tick. Combines all the time-based checks. Returns a
    summary the API can return to the operator.
    """
    expired = expire_manual_overrides(db)
    timed_out = timeout_stale_commands(db, timeout_sec)
    return {
        "expired_manual_overrides": expired,
        "timed_out_commands": timed_out,
    }
