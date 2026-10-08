"""A command the backend sent to the physical controller, awaiting ACK."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import CommandStatus


class PendingCommand(Base):
    __tablename__ = "pending_command"
    __table_args__ = (
        Index("ix_cmd_junction_status", "junction_id", "status"),
    )

    command_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    junction_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("junction.id", ondelete="CASCADE")
    )
    direction: Mapped[str] = mapped_column(String(8))
    requested_state: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(
        String(16), default=CommandStatus.PENDING.value
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ack_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=1)

    junction = relationship("Junction", back_populates="pending_commands")
