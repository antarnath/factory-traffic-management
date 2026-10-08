"""
Controller-side endpoints.

Spec §10:
    POST /api/controller-events    → ACK / NACK / TIMEOUT from the controller
    POST /api/junctions/{id}/commands → MANUAL_GREEN_REQUEST / RETURN_TO_AUTOMATIC
    POST /api/junctions/{id}/simulate-controller → dev-only: pretend the
                                                     controller went offline
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.rest_simulator import simulator
from app.db import get_db
from app.errors import JunctionNotFound
from app.models import Junction
from app.schemas import ControllerAckIn, ManualCommandIn
from app.services.events import process_controller_event
from app.services.manual import request_manual_green, return_to_automatic

router = APIRouter(prefix="/api", tags=["controller"])


@router.post("/controller-events")
def post_controller_event(payload: ControllerAckIn,
                          db: Session = Depends(get_db)) -> dict:
    """Ingest an ACK / NACK / TIMEOUT from the physical controller."""
    result = process_controller_event(db, payload.model_dump())
    db.commit()
    return result


@router.post("/junctions/{junction_id}/commands")
def post_command(junction_id: str,
                 payload: ManualCommandIn,
                 db: Session = Depends(get_db)) -> dict:
    """
    Operator command. Two flavours:
      - MANUAL_GREEN_REQUEST  → force a direction to GREEN (capped)
      - RETURN_TO_AUTOMATIC   → cancel any manual override
    """
    if db.get(Junction, junction_id) is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    if payload.command == "MANUAL_GREEN_REQUEST":
        if not payload.direction:
            return {"status": "invalid", "detail": "direction is required"}
        result = request_manual_green(db, junction_id, payload.direction)
    else:
        result = return_to_automatic(db, junction_id)
    db.commit()
    return result


class SimulateControllerIn(BaseModel):
    offline: bool = Field(default=True)


@router.post("/junctions/{junction_id}/simulate-controller")
def simulate_controller(junction_id: str,
                        payload: SimulateControllerIn,
                        db: Session = Depends(get_db)) -> dict:
    """Dev-only: pretend the controller for this junction went online/offline."""
    if db.get(Junction, junction_id) is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    simulator.set_offline(junction_id, payload.offline)
    return {
        "junction": junction_id,
        "offline": payload.offline,
        "is_offline_now": simulator.is_offline(junction_id),
    }