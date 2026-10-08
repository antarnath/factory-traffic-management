"""
Phase scheduler — picks which direction(s) should receive GREEN next in
AUTOMATIC mode.

The spec says (§5):
    "A direction containing more vehicles should normally receive higher
     scheduling priority. Vehicle type should also influence scheduling.
     The system should prevent lower-priority traffic from waiting
     indefinitely."

We honour all three rules with a weighted score and a starvation bonus.

    score = 0.5 * priority_score
          + 1.0 * queue_size
          + 0.2 * waiting_seconds
          + (10_000 if waiting_seconds >= starvation_threshold else 0)

The 10_000 bonus is a guaranteed win — it dwarfs every other factor and
ensures no direction waits forever.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

# How much each vehicle type "costs" in priority weight.
# EMERGENCY is set deliberately high so that a single emergency vehicle
# outscores a flood of normal traffic. The state machine also preempts
# on emergency regardless of scheduler output; this is a belt-and-suspenders
# guarantee for the AUTOMATIC path.
VEHICLE_PRIORITY_WEIGHT: dict[str, int] = {
    "EMERGENCY":        1_000_000,
    "TRUCK":                  20,
    "FORKLIFT":               10,
    "EMPLOYEE_VEHICLE":        5,
}

# Weight coefficients in the score formula. Tunable; keep priority modest
# (so a flood of low-priority vehicles doesn't outrank a single emergency)
# and waiting time non-trivial so queues do drain.
COEF_PRIORITY = 0.5
COEF_SIZE     = 1.0
COEF_WAITING  = 0.2
STARVATION_BONUS = 10_000  # anything >= starvation_threshold gets this


@dataclass
class DirectionQueue:
    """Aggregated state of vehicles waiting at one direction."""

    direction: str
    counts: dict[str, int]              # {"TRUCK": 2, "FORKLIFT": 1, ...}
    oldest_arrived_at: datetime | None

    @property
    def size(self) -> int:
        return sum(self.counts.values())

    @property
    def priority_score(self) -> int:
        return sum(
            VEHICLE_PRIORITY_WEIGHT.get(v, 0) * c
            for v, c in self.counts.items()
        )

    @property
    def waiting_sec(self) -> float:
        if not self.oldest_arrived_at:
            return 0.0
        now = datetime.now(timezone.utc)
        # If the timestamp is naive, treat as UTC.
        ts = self.oldest_arrived_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts).total_seconds())


def score_direction(dq: DirectionQueue, starvation_threshold: int) -> float:
    """Higher score = more deserving of GREEN."""
    base = (
        COEF_PRIORITY * dq.priority_score
        + COEF_SIZE * dq.size
        + COEF_WAITING * dq.waiting_sec
    )
    if dq.waiting_sec >= starvation_threshold:
        base += STARVATION_BONUS
    return base


def pick_next_phase(queues: Iterable[DirectionQueue],
                    current_phase: set[str],
                    min_green_satisfied: bool,
                    starvation_threshold: int,
                    ) -> set[str] | None:
    """
    Decide which directions should be GREEN next.

    Returns:
        - `None` if there's no queue at all (no decision to make).
        - `current_phase` if we should hold the current phase (either
          because `min_green_satisfied` is False — i.e. the current
          phase has not been green long enough — or because the best
          candidate is already in `current_phase`).
        - `{direction}` with the winning direction otherwise.

    Args:
        queues: aggregated per-direction state.
        current_phase: directions currently GREEN.
        min_green_satisfied: has the current phase been GREEN for at
            least `cfg.min_green_sec`? If False, we don't switch.
        starvation_threshold: seconds; a direction that has been
            waiting at least this long gets the guaranteed-win bonus.
    """
    queues = list(queues)
    if not queues:
        return None

    # Don't flip-flop: hold current phase until min_green elapsed.
    if not min_green_satisfied and current_phase:
        return current_phase

    # Find the highest-scoring direction.
    best = max(queues, key=lambda q: score_direction(q, starvation_threshold))
    best_score = score_direction(best, starvation_threshold)

    # If the best direction is already green and there's no other
    # direction with a higher score, hold the current phase.
    if best.direction in current_phase:
        current_best = max(
            (score_direction(q, starvation_threshold)
             for q in queues if q.direction in current_phase),
            default=-1.0,
        )
        if best_score <= current_best:
            return current_phase

    return {best.direction}
