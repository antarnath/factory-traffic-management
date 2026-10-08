"""Manual traffic-control command payloads."""
from pydantic import BaseModel, Field


class ManualCommandIn(BaseModel):
    command: str = Field(pattern="^(MANUAL_GREEN_REQUEST|RETURN_TO_AUTOMATIC)$")
    direction: str | None = None
