"""
Sensor and device event handlers.

These are called by the API layer when a vehicle-detection event, a
controller-ACK, or a device-failure event arrives. They must be:

  - Idempotent on `event_id`        (a duplicate submit is a no-op).
  - Out-of-order tolerant           (a late `sequence_no` is dropped).
  - Concurrency-safe                (everything goes through junction_lock).
  - Audit-logged                    (every decision is recorded).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controllers.rest_simulator import simulator
from app.models import Junction, PendingCommand, QueueEntry, Signal
from app.services.concurrency import junction_lock
from app.services.orchestrator import _audit, _now, step_junction


# =====================================================================
#   Vehicle events  (VEHICLE_ARRIVED, VEHICLE_CLEARED)
# =====================================================================


def process_vehicle_event(db: Session, payload: dict[str, Any]) -> dict:
    """
    Handle a single vehicle event. Returns a result dict for the API.

    Result keys:
        status: "processed" | "already_processed" | "out_of_order" |
                "invalid" | "ok"
        event_id: echoed back so the client can correlate
    """
    event_id     = payload.get("event_id")
    junction_id  = payload.get("junction_id")
    direction    = payload.get("direction")
    event_type   = payload.get("event_type")
    vehicle_id   = payload.get("vehicle_id")
    vehicle_type = payload.get("vehicle_type")
    sequence_no  = payload.get("sequence_no")
    timestamp    = payload.get("timestamp")

    # --- input sanity (Pydantic has already done most of this, but be defensive) ---
    if not all([event_id, junction_id, direction, event_type,
                vehicle_id, vehicle_type, sequence_no is not None, timestamp]):
        return {"status": "invalid", "event_id": event_id, "detail": "missing fields"}

    with junction_lock(db, junction_id) as junction:
        # 1. Idempotency on event_id ------------------------------------
        existing = (db.query(QueueEntry)
                      .filter(QueueEntry.event_id == event_id)
                      .one_or_none())
        if existing is not None:
            _audit(db, "DUPLICATE_EVENT_IGNORED", junction, direction,
                   {"event_id": event_id, "event_type": event_type})
            return {"status": "already_processed", "event_id": event_id}

        # 2. Out-of-order detection (per junction+direction) -------------
        last_seq = (db.query(QueueEntry.sequence_no)
                      .filter(QueueEntry.junction_id == junction_id,
                              QueueEntry.direction == direction)
                      .order_by(QueueEntry.sequence_no.desc())
                      .first())
        if last_seq is not None and sequence_no < last_seq[0]:
            _audit(db, "OUT_OF_ORDER_IGNORED", junction, direction,
                   {"event_id": event_id, "sequence_no": sequence_no,
                    "last_sequence_no": last_seq[0]})
            return {"status": "out_of_order", "event_id": event_id}

        # 3. Apply the event --------------------------------------------
        if event_type == "VEHICLE_ARRIVED":
            entry = QueueEntry(
                junction_id=junction_id,
                direction=direction,
                vehicle_type=vehicle_type,
                vehicle_id=vehicle_id,
                arrived_at=timestamp,
                event_id=event_id,
                sequence_no=sequence_no,
            )
            try:
                db.add(entry)
                db.flush()
            except IntegrityError:
                # Race: another request with the same event_id landed first.
                db.rollback()
                return {"status": "already_processed", "event_id": event_id}

            _audit(db, "VEHICLE_ARRIVED", junction, direction,
                   {"vehicle_id": vehicle_id, "vehicle_type": vehicle_type,
                    "sequence_no": sequence_no})

            # Emergency preemption
            if vehicle_type == "EMERGENCY":
                junction.mode = "EMERGENCY"
                junction.emergency_dir = direction
                _audit(db, "EMERGENCY_DETECTED", junction, direction,
                       {"vehicle_id": vehicle_id})

        elif event_type == "VEHICLE_CLEARED":
            # Match the oldest un-cleared entry in this direction.
            # We could also try to match by vehicle_id; both are reasonable
            # interpretations of the spec. Going with FIFO for simplicity.
            entry = (db.query(QueueEntry)
                       .filter(QueueEntry.junction_id == junction_id,
                               QueueEntry.direction == direction,
                               QueueEntry.cleared == False)  # noqa: E712
                       .order_by(QueueEntry.arrived_at.asc())
                       .first())
            if entry is not None:
                entry.cleared = True
                _audit(db, "VEHICLE_CLEARED", junction, direction,
                       {"vehicle_id": vehicle_id,
                        "cleared_queue_entry_id": entry.id,
                        "cleared_vehicle_id": entry.vehicle_id})
            else:
                _audit(db, "CLEARED_WITHOUT_ARRIVAL", junction, direction,
                       {"vehicle_id": vehicle_id})

            # End the emergency when the emergency direction's queue drains.
            if (junction.mode == "EMERGENCY"
                    and junction.emergency_dir == direction
                    and not _has_open_queue(db, junction_id, direction)):
                junction.mode = "AUTOMATIC"
                junction.emergency_dir = ""
                _audit(db, "EMERGENCY_CLEARED", junction, direction)
        else:
            return {"status": "invalid", "event_id": event_id,
                    "detail": f"unknown event_type {event_type!r}"}

        # 4. Run a decision cycle ---------------------------------------
        step_junction(db, junction_id)
        return {"status": "processed", "event_id": event_id}


def _has_open_queue(db: Session, junction_id: str, direction: str) -> bool:
    return (db.query(QueueEntry)
              .filter(QueueEntry.junction_id == junction_id,
                      QueueEntry.direction == direction,
                      QueueEntry.cleared == False)  # noqa: E712
              .first()) is not None


# =====================================================================
#   Device events  (controller online/offline, sensor failure)
# =====================================================================


def process_device_event(db: Session, payload: dict[str, Any]) -> dict:
    """
    Handle a device-status change (controller, signal, sensor).

    Currently the spec only defines controller status effects, but the
    function is structured to accept any device_type.
    """
    junction_id = payload.get("junction_id")
    device_type = payload.get("device_type")
    status      = payload.get("status")
    direction   = payload.get("direction") or ""

    if not all([junction_id, device_type, status]):
        return {"status": "invalid", "detail": "missing fields"}

    with junction_lock(db, junction_id) as junction:
        if device_type == "SIGNAL_CONTROLLER":
            junction.controller_status = status
            if status in ("OFFLINE", "DEGRADED"):
                junction.mode = "DEGRADED"
            elif status == "ONLINE" and junction.mode == "DEGRADED":
                # Recover — go back to automatic.
                junction.mode = "AUTOMATIC"
        _audit(db, f"DEVICE_{status}", junction, direction,
               {"device_type": device_type})
        return {"status": "ok", "junction_id": junction_id, "device_type": device_type}


# =====================================================================
#   Controller ACK / NACK / TIMEOUT
# =====================================================================


def process_controller_event(db: Session, payload: dict[str, Any]) -> dict:
    """
    Handle an ACK/NACK/TIMEOUT coming back from the physical (or simulated)
    controller.
    """
    command_id   = payload.get("command_id")
    junction_id  = payload.get("junction_id")
    status       = payload.get("status")           # "ACK" | "NACK" | "TIMEOUT"
    actual_state = payload.get("actual_state")

    if not all([command_id, junction_id, status]):
        return {"status": "invalid", "detail": "missing fields"}

    with junction_lock(db, junction_id) as junction:
        cmd = (db.query(PendingCommand)
                 .filter_by(command_id=command_id)
                 .one_or_none())
        if cmd is None:
            return {"status": "unknown_command", "command_id": command_id}

        cmd.status = status
        if status == "ACK":
            cmd.ack_at = _now()
            # Update the actual state of the signal so the dashboard
            # reflects physical reality.
            sig = (db.query(Signal)
                     .filter(Signal.junction_id == junction_id,
                             Signal.direction == cmd.direction)
                     .one_or_none())
            if sig is not None and actual_state:
                sig.actual_state = actual_state
                sig.last_known_good = actual_state
            simulator.deliver_ack(command_id, actual_state or "")
            _audit(db, "CONTROLLER_ACK", junction, cmd.direction,
                   {"command_id": command_id, "actual_state": actual_state})
        else:
            _audit(db, f"CONTROLLER_{status}", junction, cmd.direction,
                   {"command_id": command_id})
            if status == "TIMEOUT":
                junction.controller_status = "DEGRADED"

        return {"status": "ok", "command_id": command_id, "result": status}
