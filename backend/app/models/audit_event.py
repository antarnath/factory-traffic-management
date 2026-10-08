"""Append-only audit log of important system events."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_junction_ts", "junction_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(48))
    junction_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("junction.id", ondelete="CASCADE"), nullable=True
    )
    direction: Mapped[str] = mapped_column(String(8), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    junction = relationship("Junction", back_populates="audit_events")
