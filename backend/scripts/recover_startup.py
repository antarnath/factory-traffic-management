"""
Startup recovery script — runs once after a restart.

Spec §14 says: "After an unclean shutdown, the system must be safe on
restart. Any signal whose actual_state is unknown must be forced RED; any
junction left in MANUAL or EMERGENCY mode without an active override
must be returned to AUTOMATIC; any PENDING command older than the
timeout must be marked TIMEOUT."

This script is idempotent. Run it with:

    cd backend
    python -m scripts.recover_startup

It writes one audit event per junction summarizing what it did.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import AuditEvent, Junction, PendingCommand, Signal
from app.services.orchestrator import _now


TIMEOUT_DEFAULT_SEC = 5


def _mark_timed_out(db, cmd: PendingCommand) -> None:
    cmd.status = "TIMEOUT"


def recover_once(timeout_sec: int = TIMEOUT_DEFAULT_SEC) -> dict:
    """
    Run the full recovery pass. Returns a summary dict suitable for logging.
    """
    summary = {
        "forced_red_signals": 0,
        "cleared_manual_overrides": 0,
        "cleared_emergencies": 0,
        "timed_out_commands": 0,
        "degraded_junctions": 0,
    }
    now = _now()

    with SessionLocal() as db:
        # 1. Force unknown actual_state signals to RED.
        #    We treat any non-RED actual_state as suspect on restart because
        #    we can't tell what the lights were actually showing.
        bad_signals = (db.query(Signal)
                         .filter(Signal.actual_state != "RED")
                         .all())
        for sig in bad_signals:
            sig.actual_state = "RED"
            sig.last_known_good = "RED"
            summary["forced_red_signals"] += 1

        # 2. Reset MANUAL mode unless there's an override that's still
        #    in the future. After a restart we can't honor a manual override
        #    because the operator may be gone.
        for j in db.query(Junction).all():
            junction_changed = False
            if j.mode == "MANUAL":
                # Without an active operator we always revert to AUTOMATIC.
                j.mode = "AUTOMATIC"
                j.manual_override_dir = ""
                j.manual_override_until = None
                summary["cleared_manual_overrides"] += 1
                junction_changed = True

            if j.mode == "EMERGENCY":
                # An emergency that survived a restart is stale.
                j.mode = "AUTOMATIC"
                j.emergency_dir = ""
                summary["cleared_emergencies"] += 1
                junction_changed = True

            if junction_changed:
                db.add(AuditEvent(
                    event_type="STARTUP_RECOVERY",
                    junction_id=j.id,
                    direction="",
                    payload={"summary": dict(summary)},
                    timestamp=now,
                    created_at=now,
                ))

            # 3. Time out stale pending commands.
            for cmd in (db.query(PendingCommand)
                          .filter(PendingCommand.junction_id == j.id,
                                  PendingCommand.status.in_(["PENDING", "SENT"]))
                          .all()):
                sent_at = cmd.sent_at
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
                if (now - sent_at).total_seconds() >= timeout_sec:
                    _mark_timed_out(db, cmd)
                    j.controller_status = "DEGRADED"
                    summary["timed_out_commands"] += 1
                    summary["degraded_junctions"] += 1

        db.commit()
        print(f"Recovery complete: {summary}")
        return summary


def main() -> None:
    recover_once()


if __name__ == "__main__":
    main()