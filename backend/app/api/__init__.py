"""
FastAPI routers.

Each module under this package owns one logical slice of the API surface.
`register_routers(app)` wires them all into the FastAPI app.
"""
from fastapi import FastAPI

from app.api.controller_events import router as controller_router
from app.api.history import router as history_router
from app.api.junctions import router as junctions_router
from app.api.maintenance import router as maintenance_router
from app.api.sensor_events import router as sensor_events_router


def register_routers(app: FastAPI) -> None:
    app.include_router(junctions_router)
    app.include_router(sensor_events_router)
    app.include_router(controller_router)
    app.include_router(history_router)
    app.include_router(maintenance_router)


__all__ = ["register_routers"]
