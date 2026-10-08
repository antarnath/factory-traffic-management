"""
Junction CRUD endpoints.

Spec §10 calls for:
    GET  /api/junctions              → list
    GET  /api/junctions/{id}         → single junction
    POST /api/junctions              → create (idempotent on id)
    GET  /api/junctions/{id}/status  → full status snapshot
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import JunctionNotFound
from app.models import Junction, JunctionConfig, PendingCommand, Signal
from app.models.enums import SignalState
from app.schemas import JunctionCreate, JunctionOut, JunctionStatusOut
from app.services.orchestrator import step_junction
from app.services.status import build_junction_status

router = APIRouter(prefix="/api/junctions", tags=["junctions"])


@router.get("", response_model=list[JunctionOut])
def list_junctions(db: Session = Depends(get_db)) -> list[Junction]:
    return db.query(Junction).order_by(Junction.id).all()


@router.get("/{junction_id}", response_model=JunctionOut)
def get_junction(junction_id: str, db: Session = Depends(get_db)) -> Junction:
    j = db.get(Junction, junction_id)
    if j is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    return j


@router.post("", response_model=JunctionOut, status_code=status.HTTP_201_CREATED)
def create_junction(payload: JunctionCreate, db: Session = Depends(get_db)) -> Junction:
    """Idempotent on `id`: if it already exists, return the existing row."""
    existing = db.get(Junction, payload.id)
    if existing is not None:
        return existing

    junction = Junction(id=payload.id, name=payload.name)
    db.add(junction)
    # Default config: stock timings, no custom phases.
    junction.config = JunctionConfig(
        junction_id=payload.id,
        green_duration_sec=30,
        yellow_duration_sec=5,
        all_red_duration_sec=2,
        min_green_sec=10,
        starvation_threshold_sec=60,
    )
    # Default signals: one per cardinal direction, all RED.
    for direction in ("NORTH", "SOUTH", "EAST", "WEST"):
        db.add(Signal(
            junction_id=payload.id,
            direction=direction,
            desired_state=SignalState.RED.value,
            actual_state=SignalState.RED.value,
            last_known_good=SignalState.RED.value,
        ))
    try:
        db.commit()
    except IntegrityError:
        # Race: another POST landed first. Roll back and return the winner.
        db.rollback()
        existing = db.get(Junction, payload.id)
        if existing is not None:
            return existing
        raise
    db.refresh(junction)
    return junction


@router.get("/{junction_id}/status", response_model=JunctionStatusOut)
def get_junction_status(junction_id: str,
                        db: Session = Depends(get_db)) -> JunctionStatusOut:
    j = db.get(Junction, junction_id)
    if j is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    return build_junction_status(db, j)


@router.post("/{junction_id}/step")
def step(junction_id: str, db: Session = Depends(get_db)) -> dict:
    """Force one decision cycle. Useful for debugging / admin tools."""
    j = db.get(Junction, junction_id)
    if j is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    summary = step_junction(db, junction_id)
    db.commit()
    return summary


@router.get("/{junction_id}/pending-command")
def get_pending_command(junction_id: str,
                        db: Session = Depends(get_db)) -> dict:
    """
    Return the most recent PENDING/SENT command_id for this junction,
    or `{"command_id": null}` if there isn't one. Used by the dashboard's
    "send controller ACK" simulation button.
    """
    if db.get(Junction, junction_id) is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    cmd = (db.query(PendingCommand)
             .filter(PendingCommand.junction_id == junction_id,
                     PendingCommand.status.in_(["PENDING", "SENT"]))
             .order_by(PendingCommand.sent_at.desc())
             .first())
    return {"command_id": cmd.command_id if cmd else None}
