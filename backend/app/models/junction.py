"""Junction — one physical intersection the system controls."""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import DeviceStatus, JunctionMode


class Junction(Base):
    __tablename__ = "junction"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. "A"
    name: Mapped[str] = mapped_column(String(64), default="")
    mode: Mapped[str] = mapped_column(String(16), default=JunctionMode.AUTOMATIC.value)
    phase: Mapped[str] = mapped_column(String(16), default="ALL_RED")
    controller_status: Mapped[str] = mapped_column(
        String(16), default=DeviceStatus.UNKNOWN.value
    )
    manual_override_dir: Mapped[str] = mapped_column(String(8), default="")
    manual_override_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    emergency_dir: Mapped[str] = mapped_column(String(8), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    config = relationship(
        "JunctionConfig",
        back_populates="junction",
        uselist=False,
        cascade="all, delete-orphan",
    )
    signals = relationship(
        "Signal", back_populates="junction", cascade="all, delete-orphan"
    )
    queue_entries = relationship(
        "QueueEntry", back_populates="junction", cascade="all, delete-orphan"
    )
    pending_commands = relationship(
        "PendingCommand", back_populates="junction", cascade="all, delete-orphan"
    )
    audit_events = relationship(
        "AuditEvent", back_populates="junction", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Junction {self.id} mode={self.mode}>"
