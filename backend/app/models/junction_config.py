"""Per-junction timing & phase definition. Editable, persistent."""
from typing import Any

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class JunctionConfig(Base):
    __tablename__ = "junction_config"

    junction_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("junction.id", ondelete="CASCADE"),
        primary_key=True,
    )
    green_duration_sec:       Mapped[int] = mapped_column(Integer, default=30)
    yellow_duration_sec:      Mapped[int] = mapped_column(Integer, default=5)
    all_red_duration_sec:     Mapped[int] = mapped_column(Integer, default=2)
    min_green_sec:            Mapped[int] = mapped_column(Integer, default=10)
    starvation_threshold_sec: Mapped[int] = mapped_column(Integer, default=60)
    phases_json: Mapped[list[Any]] = mapped_column(JSON, default=list)

    junction = relationship("Junction", back_populates="config")
