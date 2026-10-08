"""
Manual override — sets a junction into MANUAL mode and forces a direction
to GREEN for a limited time.

Spec §6 says: "An authorized operator may manually request a GREEN signal
for a chosen direction. Manual control is temporary; the system returns to
AUTOMATIC after the configured maximum duration unless renewed."

The orchestrator and the safety module already guarantee that the transition
is safe (GREEN → YELLOW → ALL_RED → GREEN). This module just:
  1. Records the request on the junction row (so the state machine sees it).
  2. Sets a `manual_override_until` deadline.
  3. Lets the orchestrator's normal decision cycle do the actual signal work.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.errors import JunctionNotFound
from app.models import Junction
from app.services.concurrency import junction_lock
from app.services.orchestrator import _audit, _now, step_junction


def _now() -> datetime:
    return datetime.now(timezone.utc)


def request_manual_green(db: Session,
                          junction_id: str,
                          direction: str,
                          max_duration_sec: int = 60) -> dict:
    """
    Force a direction to GREEN for at most `max_duration_sec` seconds.

    The transition is still subject to the safe sequence
    (GREEN → YELLOW → ALL_RED → GREEN) — see `plan_transition`.

    Returns a small summary dict suitable for the API response.
    """
    with junction_lock(db, junction_id) as junction:
        if junction is None:
            raise JunctionNotFound(junction_id)
        cfg = junction.config
        # Cap the requested duration at the configured max; the smaller wins.
        cap = (cfg.manual_override_max_sec
               if cfg and getattr(cfg, "manual_override_max_sec", None)
               else max_duration_sec)
        until = _now() + timedelta(seconds=min(max_duration_sec, cap))

        junction.mode = "MANUAL"
        junction.manual_override_dir = direction
        junction.manual_override_until = until

        _audit(db, "MANUAL_OVERRIDE_REQUESTED", junction, direction,
               {"until": until.isoformat()})

        # Run a decision cycle so the orchestrator plans & applies the
        # transition immediately (rather than waiting for the next event).
        step_junction(db, junction_id)
        return {
            "junction": junction_id,
            "mode": junction.mode,
            "direction": direction,
            "until": until.isoformat(),
        }


def return_to_automatic(db: Session, junction_id: str) -> dict:
    """
    Cancel any active manual override. Safe to call even if no override is
    active — the function is idempotent.
    """
    with junction_lock(db, junction_id) as junction:
        if junction is None:
            raise JunctionNotFound(junction_id)
        was_manual = junction.mode == "MANUAL"
        junction.mode = "AUTOMATIC"
        junction.manual_override_dir = ""
        junction.manual_override_until = None
        if was_manual:
            _audit(db, "RETURNED_TO_AUTOMATIC", junction, "")
        # Run a decision cycle so the next direction gets chosen.
        step_junction(db, junction_id)
        return {"junction": junction_id, "mode": junction.mode}
