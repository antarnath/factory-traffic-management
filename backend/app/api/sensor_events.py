"""
Sensor event ingestion endpoints.

Spec §10:
    POST /api/sensor-events   → VEHICLE_ARRIVED / VEHICLE_CLEARED
    POST /api/device-events   → device status changes
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DeviceEventIn, VehicleEventIn
from app.services.events import process_device_event, process_vehicle_event

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/sensor-events")
def post_sensor_event(payload: VehicleEventIn,
                      db: Session = Depends(get_db)) -> dict:
    """
    Ingest one vehicle event.

    Returns:
        {"status": "processed" | "already_processed" | "out_of_order" | ...,
         "event_id": "..."}
    """
    result = process_vehicle_event(db, payload.model_dump())
    db.commit()
    return result


@router.post("/device-events")
def post_device_event(payload: DeviceEventIn,
                      db: Session = Depends(get_db)) -> dict:
    """
    Ingest one device-status event (controller online/offline, etc.).
    """
    result = process_device_event(db, payload.model_dump())
    db.commit()
    return result
