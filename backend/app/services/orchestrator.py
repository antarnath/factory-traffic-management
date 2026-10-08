"""
Orchestrator — the single place that wires domain logic to the database.

The domain services (`safety`, `transitions`, `scheduler`, `state_machine`)
are pure functions. The orchestrator is the *only* module that:

  - reads a Junction row,
  - builds a JunctionSnapshot,
  - calls `next_action()`,
  - mutates Signal / Junction / AuditEvent rows,
  - sends commands to the physical controller.

This split keeps the domain logic trivially testable in isolation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.controllers.rest_simulator import simulator
from app.models import AuditEvent, Junction, PendingCommand, Signal
from app.services.concurrency import junction_lock
from app.services.queue import build_direction_queues
from app.services.safety import GREEN, RED, YELLOW
from app.services.state_machine import (
    ACTION_AUTOMATIC,
    ACTION_EMERGENCY_PREEMPT,
    ACTION_HOLD,
    ACTION_MANUAL,
    JunctionSnapshot,
    next_action,
)
from app.services.transitions import plan_transition


# ------------------------------- helpers ---------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, event_type: str, junction: Junction,
           direction: str = "", payload: dict | None = None) -> None:
    """Append a row to the audit log. Caller owns the transaction."""
    db.add(AuditEvent(
        event_type=event_type,
        junction_id=junction.id,
        direction=direction,
        payload=payload or {},
        timestamp=_now(),
        created_at=_now(),
    ))


def _send_to_controller(db: Session, junction: Junction,
                        direction: str, requested_state: str) -> str | None:
    """
    Create a PendingCommand row, ask the controller to act on it.
    Returns the command_id, or None if the controller is offline.
    """
    command_id = f"cmd-{junction.id}-{uuid.uuid4().hex[:12]}"
    res = simulator.send_command(command_id, junction.id, direction, requested_state)
    if not res.accepted:
        junction.controller_status = "OFFLINE"
        junction.mode = "DEGRADED"
        _audit(db, "CONTROLLER_OFFLINE_BLOCKED_COMMAND", junction,
               direction, {"command_id": command_id})
        return None
    db.add(PendingCommand(
        command_id=command_id,
        junction_id=junction.id,
        direction=direction,
        requested_state=requested_state,
        sent_at=_now(),
        attempts=1,
    ))
    return command_id


def _min_green_satisfied(db: Session, junction: Junction,
                         min_green_sec: int) -> bool:
    """
    Returns True if the current green phase has been green for at least
    `min_green_sec`. Used to prevent flip-flopping.

    We use the `payload` JSON column to look for SIGNAL_CHANGED events
    whose `to` field is GREEN. The JSON key access is done in Python
    after fetching candidates — there are very few rows in the audit
    log per junction, so this is cheap and portable across SQL dialects.
    """
    candidates = (db.query(AuditEvent)
                    .filter(AuditEvent.junction_id == junction.id,
                            AuditEvent.event_type == "SIGNAL_CHANGED")
                    .order_by(AuditEvent.timestamp.desc())
                    .limit(50)
                    .all())
    for row in candidates:
        if (row.payload or {}).get("to") == GREEN:
            ts = row.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (_now() - ts).total_seconds() >= min_green_sec
    return True  # no green has ever been commanded → don't block


# ------------------------------- main entry -------------------------------


def step_junction(db: Session, junction_id: str) -> dict:
    """
    Run a single decision cycle for one junction.

    1. Acquire the per-junction row lock.
    2. Read current state, build a JunctionSnapshot.
    3. Ask the state machine what to do.
    4. Apply the action (mutate Signal rows, send controller commands,
       write audit events).
    5. Return an audit-friendly summary dict.

    The caller is responsible for `db.commit()` afterwards.
    """
    with junction_lock(db, junction_id) as junction:
        cfg = junction.config
        if cfg is None:
            return {"junction": junction_id, "action": "NO_CONFIG", "ok": False}

        signals: dict[str, Signal] = {s.direction: s for s in junction.signals}
        if not signals:
            return {"junction": junction_id, "action": "NO_SIGNALS", "ok": False}

        # Read the *actual* state — that's what the physical lights are showing.
        signal_state_map = {d: s.actual_state for d, s in signals.items()}
        desired_state_map = {d: s.desired_state for d, s in signals.items()}
        current_green = {d for d, s in signal_state_map.items() if s == GREEN}

        # Build the queue aggregate from the un-cleared entries.
        queue_rows = [q for q in junction.queue_entries if not q.cleared]
        dqs = build_direction_queues(queue_rows)

        snap = JunctionSnapshot(
            junction_id=junction.id,
            mode=junction.mode,
            current_phase=current_green,
            signals=signal_state_map,
            queues=dqs,
            emergency_dir=junction.emergency_dir or None,
            manual_override_dir=junction.manual_override_dir or None,
            min_green_satisfied=_min_green_satisfied(db, junction, cfg.min_green_sec),
            starvation_threshold=cfg.starvation_threshold_sec,
        )
        action = next_action(snap)

        summary: dict = {
            "junction": junction_id,
            "action": action.action,
            "target": sorted(action.target_greens) if action.target_greens else None,
            "reason": action.reason,
            "ok": True,
        }

        if action.action == ACTION_HOLD or action.target_greens is None:
            return summary

        # Plan the safe sequence and apply only the FIRST step. The next
        # events (more vehicles, a manual command, an ACK) will advance it.
        # This is what the spec means by "remain consistent when multiple
        # events arrive close together" — we don't jump to the target,
        # we take it one step at a time.
        try:
            sequence = plan_transition(desired_state_map, action.target_greens)
        except ValueError as e:
            _audit(db, "UNSAFE_TRANSITION_REJECTED", junction, "",
                   {"error": str(e)})
            summary["ok"] = False
            return summary

        next_desired = sequence[1] if len(sequence) > 1 else sequence[0]
        changed = False
        for direction, new_state in next_desired.items():
            sig = signals.get(direction)
            if sig is None or sig.desired_state == new_state:
                continue
            old = sig.desired_state
            sig.desired_state = new_state
            sig.last_changed_at = _now()
            _audit(db, "SIGNAL_CHANGED", junction, direction,
                   {"from": old, "to": new_state, "source": action.action})
            changed = True

        # For any direction whose desired_state actually changed, send the
        # command to the controller. We send on every transition step
        # (RED→YELLOW, YELLOW→GREEN, RED→GREEN) — the safe-transition logic
        # in `transitions` guarantees we never send conflicting greens in
        # the same step.
        for direction, new_state in next_desired.items():
            sig = signals.get(direction)
            if sig is None:
                continue
            if sig.desired_state != new_state:
                continue  # not changed (shouldn't happen, defensive)
            if new_state not in (RED, YELLOW, GREEN):
                continue
            _send_to_controller(db, junction, direction, new_state)

        # Update the human-readable phase label.
        if changed:
            junction.phase = _phase_label(action.target_greens,
                                           current_green,
                                           signal_state_map)

        return summary


def _phase_label(target: Iterable[str], current: set[str],
                 actual: dict[str, str]) -> str:
    """
    Produce a short label like 'EW_GREEN' or 'ALL_RED' for the junction.phase
    column (used by the dashboard and audit log).
    """
    target = set(target)
    # If everything is RED right now, we are in the clearance phase.
    if all(s == RED for s in actual.values()):
        return "ALL_RED"
    if target and "NORTH" in target or "SOUTH" in target:
        if all(d in {"NORTH", "SOUTH"} for d in target):
            return "NS_GREEN"
    if target and ("EAST" in target or "WEST" in target):
        if all(d in {"EAST", "WEST"} for d in target):
            return "EW_GREEN"
    return "TRANSITION"


def step_all_junctions(db: Session) -> list[dict]:
    """Run one decision cycle for every junction. Returns the per-junction summaries."""
    out: list[dict] = []
    for j in db.query(Junction).all():
        out.append(step_junction(db, j.id))
    db.commit()
    return out
