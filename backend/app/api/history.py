"""
History endpoint — paginated audit log for a single junction.

Spec §10:
    GET /api/junctions/{id}/history?limit=50&offset=0
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import JunctionNotFound
from app.models import AuditEvent, Junction

router = APIRouter(prefix="/api/junctions", tags=["history"])


@router.get("/{junction_id}/history")
def get_history(junction_id: str,
                limit: int = Query(50, ge=1, le=500),
                offset: int = Query(0, ge=0),
                db: Session = Depends(get_db)) -> dict:
    if db.get(Junction, junction_id) is None:
        raise JunctionNotFound(f"Junction {junction_id!r} not found",
                               {"junction_id": junction_id})
    q = (db.query(AuditEvent)
           .filter(AuditEvent.junction_id == junction_id)
           .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc()))
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "junction": junction_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "id": r.id,
                "event_type": r.event_type,
                "direction": r.direction,
                "payload": r.payload,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }
