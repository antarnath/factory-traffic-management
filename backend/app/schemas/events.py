"""Inbound event payloads from sensors and the controller."""
from datetime import datetime

from pydantic import BaseModel, Field

DIRECTIONS: tuple[str, ...] = ("NORTH", "SOUTH", "EAST", "WEST")
VEHICLE_TYPES: tuple[str, ...] = (
    "FORKLIFT",
    "TRUCK",
    "EMPLOYEE_VEHICLE",
    "EMERGENCY",
)
DEVICE_TYPES: tuple[str, ...] = ("SIGNAL", "SENSOR", "SIGNAL_CONTROLLER")
DEVICE_STATUSES: tuple[str, ...] = (
    "ONLINE", "OFFLINE", "DEGRADED", "WARNING", "UNKNOWN",
)
SIGNAL_STATES: tuple[str, ...] = ("RED", "YELLOW", "GREEN")
ACK_STATUSES: tuple[str, ...] = ("ACK", "NACK", "TIMEOUT")


class VehicleEventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    junction_id: str = Field(min_length=1, max_length=16)
    direction: str
    event_type: str = Field(pattern="^(VEHICLE_ARRIVED|VEHICLE_CLEARED)$")
    vehicle_id: str
    vehicle_type: str
    sequence_no: int
    timestamp: datetime


class DeviceEventIn(BaseModel):
    event_id: str
    junction_id: str
    direction: str | None = None
    device_type: str
    status: str
    timestamp: datetime


class ControllerAckIn(BaseModel):
    command_id: str
    junction_id: str
    status: str = Field(pattern="^(ACK|NACK|TIMEOUT)$")
    actual_state: str | None = None
    timestamp: datetime
