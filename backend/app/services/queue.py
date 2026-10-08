"""
Queue helpers — convert raw QueueEntry rows into DirectionQueue aggregates
for the scheduler.

This is a pure-Python module. It accepts any iterable of objects that
expose `.direction`, `.vehicle_type`, and `.arrived_at` — that means it
works with SQLAlchemy ORM rows in production and with plain dataclasses
in tests.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from typing import Iterable

from app.services.scheduler import DirectionQueue


def _as_utc(ts):
    """Coerce a possibly-naive datetime into a tz-aware UTC one."""
    if ts is None:
        return None
    if getattr(ts, "tzinfo", None) is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def build_direction_queues(queue_rows: Iterable) -> list[DirectionQueue]:
    """
    Group un-cleared queue rows by direction and return one DirectionQueue per
    non-empty direction.

    The caller is responsible for filtering out cleared entries before
    passing them in (the queue_rows list may also be the full set; in that
    case we ignore cleared ones by attribute — see note below).
    """
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    oldest: dict[str, object] = {}

    for row in queue_rows:
        # Skip cleared entries if the row exposes the attribute.
        if getattr(row, "cleared", False):
            continue
        direction = row.direction
        vtype = row.vehicle_type
        arrived = _as_utc(row.arrived_at)

        grouped[direction][vtype] += 1
        cur = oldest.get(direction)
        if cur is None or arrived < cur:
            oldest[direction] = arrived

    return [
        DirectionQueue(
            direction=d,
            counts=dict(counts),
            oldest_arrived_at=oldest.get(d),
        )
        for d, counts in grouped.items()
        if any(counts.values())
    ]


def queue_size_per_direction(queue_rows: Iterable) -> dict[str, int]:
    """Convenience: flat dict of {direction: count} for status responses."""
    out: dict[str, int] = defaultdict(int)
    for row in queue_rows:
        if getattr(row, "cleared", False):
            continue
        out[row.direction] += 1
    return dict(out)
