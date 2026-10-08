"""
Junction status — assembles the payload the dashboard polls.

The status endpoint is the *primary* read API: it must be cheap (no writes,
no audit), self-describing (a JSON snapshot the frontend can render without
joining anything), and eventually consistent (the caller should poll
frequently, e.g. once per second).

Composition:
    1.  junction row             → mode, phase, controller_status, etc.
    2.  signals                  → desired vs actual, per direction
    3.  queue_entries            → size per direction (uncount cleared)
    4.  pending_commands (latest)→ most recent PENDING/SENT command_id

This is a pure read — no `junction_lock`, no `_audit`.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Junction, PendingCommand, QueueEntry, Signal
from app.schemas import JunctionStatusOut


def build_junction_status(db: Session, junction: Junction) -> JunctionStatusOut:
    """
    Build the dashboard-friendly status payload for a single junction.

    The caller is responsible for loading the `junction` row *and* making
    sure it still exists (we don't refresh, we trust the caller's session).
    """
    # Signals: desired vs actual, sorted by direction for stable JSON.
    signals: dict[str, Signal] = {s.direction: s for s in junction.signals}
    desired = {d: s.desired_state for d, s in signals.items()}
    actual = {d: s.actual_state for d, s in signals.items()}

    # Queue size per direction — un-cleared entries only.
    size_per_dir: dict[str, int] = {d: 0 for d in signals}
    for d, count in (
        db.query(QueueEntry.direction, func.count(QueueEntry.id))
          .filter(QueueEntry.junction_id == junction.id,
                  QueueEntry.cleared == False)  # noqa: E712
          .group_by(QueueEntry.direction)
          .all()
    ):
        size_per_dir[d] = count

    # Latest pending command (PENDING or SENT, not yet ACK/NACK).
    pending = (db.query(PendingCommand)
                 .filter(PendingCommand.junction_id == junction.id,
                         PendingCommand.status.in_(["PENDING", "SENT"]))
                 .order_by(PendingCommand.sent_at.desc())
                 .first())
    pending_id = pending.command_id if pending else None

    return JunctionStatusOut(
        junction=junction.id,
        mode=junction.mode,
        phase=junction.phase,
        controller_status=junction.controller_status,
        desired_signals=desired,
        actual_signals=actual,
        queues=size_per_dir,
        pending_command_id=pending_id,
        manual_override_active=bool(
            junction.manual_override_dir
            and junction.manual_override_until
            # We don't actually evaluate "is it still in the future" here
            # — the maintenance tick does that and clears it. This flag is
            # best read as "an override is currently set, see override_until".
        ),
        emergency_active=junction.mode == "EMERGENCY",
    )


def all_junction_statuses(db: Session) -> list[JunctionStatusOut]:
    """Convenience: build statuses for every junction. Cheap enough at 10s."""
    out: list[JunctionStatusOut] = []
    for j in db.query(Junction).all():
        out.append(build_junction_status(db, j))
    return out
