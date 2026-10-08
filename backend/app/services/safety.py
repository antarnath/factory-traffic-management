"""
Traffic-safety invariants — the four non-negotiable rules from spec §3:

  1. Conflicting traffic must never simultaneously receive GREEN.
  2. A GREEN phase must never transition directly into a conflicting GREEN phase.
  3. Manual or emergency priority must not bypass the safe signal-transition sequence.
  4. Invalid or unexpected commands must not place the junction in an unsafe state.

This module is pure Python — no FastAPI, no SQLAlchemy, no I/O. Every other
service funnels decisions through these checks before applying them.
"""
from __future__ import annotations

from typing import Mapping

# Canonical signal-state string constants. We use raw strings (not the
# SignalState enum) so this module stays importable without circular deps.
RED = "RED"
YELLOW = "YELLOW"
GREEN = "GREEN"
ALL_VALID_STATES: frozenset[str] = frozenset({RED, YELLOW, GREEN})

# Pre-defined conflict sets: a direction's GREEN conflicts with every
# direction in its set. NORTH and SOUTH share a phase, EAST and WEST share one.
DEFAULT_CONFLICTS: dict[str, frozenset[str]] = {
    "NORTH": frozenset({"EAST", "WEST"}),
    "SOUTH": frozenset({"EAST", "WEST"}),
    "EAST":  frozenset({"NORTH", "SOUTH"}),
    "WEST":  frozenset({"NORTH", "SOUTH"}),
}


def conflicts_for(direction: str,
                  conflicts: Mapping[str, frozenset[str]] | None = None) -> frozenset[str]:
    """Return the set of directions that conflict with `direction`."""
    return (conflicts or DEFAULT_CONFLICTS).get(direction, frozenset())


def is_legal_signal_map(states: Mapping[str, str],
                        conflicts: Mapping[str, frozenset[str]] | None = None) -> bool:
    """
    Rule 1: no two conflicting directions may both be GREEN simultaneously.

    `states` is a dict like {"NORTH": "GREEN", "SOUTH": "GREEN",
                              "EAST": "RED",   "WEST":  "RED"}.
    """
    conflicts = conflicts or DEFAULT_CONFLICTS
    greens = {d for d, s in states.items() if s == GREEN}
    for d in greens:
        if greens & (conflicts.get(d) or frozenset()):
            return False
    return True


def is_safe_transition(prev: Mapping[str, str],
                       next_: Mapping[str, str],
                       conflicts: Mapping[str, frozenset[str]] | None = None) -> bool:
    """
    Rule 2: a GREEN phase must never transition directly into a conflicting
    GREEN phase. We always require the previous greens to be moved out
    (YELLOW/RED) before the next greens can come up.

    Both `prev` and `next_` must already be legal signal maps (Rule 1).
    """
    conflicts = conflicts or DEFAULT_CONFLICTS

    if not is_legal_signal_map(next_, conflicts):
        return False

    prev_greens = {d for d, s in prev.items() if s == GREEN}
    next_greens = {d for d, s in next_.items() if s == GREEN}

    # If a direction is becoming GREEN, the set of directions that WERE green
    # must not conflict with it — otherwise we skipped YELLOW/ALL_RED.
    for d in next_greens:
        if prev_greens and (prev_greens & (conflicts.get(d) or frozenset())):
            return False
    return True


def assert_legal_signal_map(states: Mapping[str, str],
                            conflicts: Mapping[str, frozenset[str]] | None = None) -> None:
    """Raise ValueError if the map is not legal. Convenience wrapper."""
    if not is_legal_signal_map(states, conflicts):
        raise ValueError(f"Illegal signal map: {dict(states)}")


def assert_safe_transition(prev: Mapping[str, str],
                           next_: Mapping[str, str],
                           conflicts: Mapping[str, frozenset[str]] | None = None) -> None:
    """Raise ValueError if the transition is not safe. Convenience wrapper."""
    if not is_safe_transition(prev, next_, conflicts):
        raise ValueError(f"Unsafe transition: {dict(prev)} -> {dict(next_)}")
