"""One physical signal head per (junction, direction)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import SignalState


class Signal(Base):
    __tablename__ = "signal"
    __table_args__ = (
        UniqueConstraint("junction_id", "direction", name="uq_signal_junction_dir"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    junction_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("junction.id", ondelete="CASCADE")
    )
    direction: Mapped[str] = mapped_column(String(8))  # NORTH / SOUTH / EAST / WEST

    desired_state: Mapped[str] = mapped_column(
        String(8), default=SignalState.RED.value
    )
    actual_state: Mapped[str] = mapped_column(
        String(8), default=SignalState.RED.value
    )
    last_known_good: Mapped[str] = mapped_column(
        String(8), default=SignalState.RED.value
    )
    last_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    junction = relationship("Junction", back_populates="signals")
