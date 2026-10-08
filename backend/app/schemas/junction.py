"""Junction request/response models."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class JunctionBase(BaseModel):
    id: str = Field(min_length=1, max_length=16)
    name: str = ""


class JunctionCreate(JunctionBase):
    """Payload for POST /api/junctions."""


class JunctionOut(ORMBase):
    id: str
    name: str
    mode: str
    phase: str
    controller_status: str
    manual_override_dir: str
    manual_override_until: datetime | None = None
    emergency_dir: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
