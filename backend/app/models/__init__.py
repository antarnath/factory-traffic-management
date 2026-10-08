"""
Single import surface for all SQLAlchemy models.

Importing this package ensures every model is registered with
`app.db.Base.metadata` so Alembic's autogenerate can see them.
"""
from app.db import Base
from app.models.audit_event import AuditEvent
from app.models.enums import (
    CommandStatus,
    DeviceStatus,
    DeviceType,
    JunctionMode,
    SignalState,
    VehicleType,
)
from app.models.junction import Junction
from app.models.junction_config import JunctionConfig
from app.models.pending_command import PendingCommand
from app.models.queue_entry import QueueEntry
from app.models.signal import Signal

__all__ = [
    "Base",
    "AuditEvent",
    "CommandStatus",
    "DeviceStatus",
    "DeviceType",
    "Junction",
    "JunctionConfig",
    "JunctionMode",
    "PendingCommand",
    "QueueEntry",
    "Signal",
    "SignalState",
    "VehicleType",
]
