"""
Safe signal-state transition planner.

Implements the GREEN → YELLOW → ALL_RED → GREEN sequence required by spec §3
("A GREEN phase must never transition directly into a conflicting GREEN phase").

The planner is a *pure function*: given the current signal map and the set of
directions we want to be GREEN next, it returns the ordered list of
intermediate maps. The caller is responsible for actually applying them with
appropriate dwell times.
"""
from __future__ import annotations

from typing import Mapping

from app.services.safety import (
    GREEN,
    RED,
    YELLOW,
    DEFAULT_CONFLICTS,
    is_safe_transition,
)

# Default dwell times (seconds). Real values come from JunctionConfig.
YELLOW_DURATION_DEFAULT = 5
ALL_RED_DURATION_DEFAULT = 2


def plan_transition(current: Mapping[str, str],
                    target_greens: set[str],
                    conflicts: Mapping[str, frozenset[str]] | None = None
                    ) -> list[dict[str, str]]:
    """
    Produce the ordered list of signal maps to walk from `current` to a state
    where exactly `target_greens` are GREEN and the rest are RED.

    Sequence (with redundant steps elided):
        [0] current state (unchanged)
        [1] previous-greens → YELLOW (skipped if no current greens)
        [2] ALL RED (skipped if all signals are already RED)
        [3] target-greens → GREEN, rest RED

    Returns a list with 1 element if `current` already matches `target_greens`.

    Raises ValueError if any intermediate step would be unsafe.
    """
    conflicts = conflicts or DEFAULT_CONFLICTS
    directions = list(current.keys())

    # Already at target? No transitions needed.
    current_greens = {d for d, s in current.items() if s == GREEN}
    if current_greens == set(target_greens):
        return [dict(current)]

    sequence: list[dict[str, str]] = [dict(current)]

    # Step 1: previous-greens become YELLOW (only if there are any greens).
    if current_greens:
        step1 = dict(current)
        for d in current_greens:
            step1[d] = YELLOW
        sequence.append(step1)

    # Step 2: ALL RED (skip if we're already there).
    if any(s != RED for s in current.values()):
        step2 = {d: RED for d in directions}
        sequence.append(step2)

    # Step 3: target-greens GREEN, rest RED.
    step3 = {d: (GREEN if d in target_greens else RED) for d in directions}
    sequence.append(step3)

    for a, b in zip(sequence, sequence[1:]):
        if not is_safe_transition(a, b, conflicts):
            raise ValueError(f"Unsafe transition step: {a} -> {b}")
    return sequence


def first_step(current: Mapping[str, str],
               target_greens: set[str],
               conflicts: Mapping[str, frozenset[str]] | None = None
               ) -> dict[str, str]:
    """
    Return only the *first* map to apply. Useful when callers drive one
    step at a time (e.g. orchestrator that triggers on a timer/event).
    """
    return plan_transition(current, target_greens, conflicts)[1]


def transition_durations(junction_config) -> tuple[int, int, int]:
    """
    Read dwell times from a JunctionConfig ORM row.
    Returns (yellow_sec, all_red_sec, green_sec).
    """
    return (
        junction_config.yellow_duration_sec,
        junction_config.all_red_duration_sec,
        junction_config.green_duration_sec,
    )
