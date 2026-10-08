"""Junction status response — what the dashboard polls."""
from pydantic import BaseModel


class JunctionStatusOut(BaseModel):
    junction: str
    mode: str
    phase: str
    controller_status: str
    desired_signals: dict[str, str]
    actual_signals: dict[str, str]
    queues: dict[str, int]
    pending_command_id: str | None = None
    manual_override_active: bool = False
    emergency_active: bool = False
