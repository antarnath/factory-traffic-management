"""Shared Pydantic base types and error envelope."""
from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Base for response models that are populated from SQLAlchemy rows."""

    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
