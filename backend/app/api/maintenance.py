"""
Maintenance endpoint — runs the time-based checks (manual overrides,
controller timeouts, desired/actual reconciliation).

Spec §10:
    POST /api/maintenance/tick
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.reconcile import reconcile_all
from app.services.timeouts import run_all_maintenance

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class TickResult(BaseModel):
    expired_manual_overrides: list[str]
    timed_out_commands: list[str]
    reconciled: list[str]


@router.post("/tick", response_model=TickResult)
def tick(db: Session = Depends(get_db)) -> TickResult:
    """Run all maintenance checks once. Idempotent."""
    result = run_all_maintenance(db)
    reconciled = reconcile_all(db)
    db.commit()
    return TickResult(
        expired_manual_overrides=result["expired_manual_overrides"],
        timed_out_commands=result["timed_out_commands"],
        reconciled=reconciled,
    )
