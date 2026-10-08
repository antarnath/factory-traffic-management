"""One vehicle waiting at a junction. event_id is the idempotency key."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class QueueEntry(Base):
    __tablename__ = "queue_entry"
    __table_args__ = (
        Index("ix_queue_junction_dir_cleared", "junction_id", "direction", "cleared"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    junction_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("junction.id", ondelete="CASCADE")
    )
    direction: Mapped[str] = mapped_column(String(8))
    vehicle_type: Mapped[str] = mapped_column(String(16))
    vehicle_id: Mapped[str] = mapped_column(String(64), default="")
    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_id: Mapped[str] = mapped_column(String(64), unique=True)  # idempotency
    sequence_no: Mapped[int] = mapped_column(default=0)
    cleared: Mapped[bool] = mapped_column(Boolean, default=False)

    junction = relationship("Junction", back_populates="queue_entries")
