"""
Junction-level state machine.

The system has four operating modes (per spec §6):
    AUTOMATIC  — normal mode; the scheduler picks the next phase.
    MANUAL     — an admin has requested a specific direction GREEN.
    EMERGENCY  — an emergency vehicle is in the queue; preempts everything.
    DEGRADED   — a controller/sensor is offline; we hold the current phase.

This module answers one question for one junction:

    Given the current state, what should the system *intend* to do next?

It returns an action descriptor; the orchestrator (Phase 3) is responsible
for actually executing it. This split keeps the state machine pure and
trivially testable.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.scheduler import DirectionQueue, pick_next_phase


# --- Action types ---------------------------------------------------------

ACTION_HOLD              = "HOLD"
ACTION_AUTOMATIC         = "AUTOMATIC"
ACTION_MANUAL            = "MANUAL"
ACTION_EMERGENCY_PREEMPT = "EMERGENCY_PREEMPT"
ACTION_DEGRADED          = "DEGRADED"


@dataclass
class JunctionSnapshot:
    """A read-only view of one junction at one moment in time.

    Built by the orchestrator from a DB row, then handed to next_action().
    """

    junction_id: str
    mode: str                 # AUTOMATIC / MANUAL / EMERGENCY / DEGRADED
    current_phase: set[str]   # directions currently GREEN
    signals: dict[str, str]   # {direction: "RED"/"YELLOW"/"GREEN"}
    queues: list[DirectionQueue]
    emergency_dir: str | None
    manual_override_dir: str | None
    min_green_satisfied: bool
    starvation_threshold: int


@dataclass
class Action:
    """What the system intends to do next.

    `target_greens` is `None` for HOLD; otherwise it's the set of directions
    that *should* be GREEN once the safe transition completes.
    """

    action: str
    target_greens: set[str] | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "target_greens": sorted(self.target_greens) if self.target_greens else None,
            "reason": self.reason,
        }


def next_action(snap: JunctionSnapshot) -> Action:
    """
    Pure function. Same input → same output. No DB, no HTTP, no time side-effects.

    Decision order (highest priority first):
        1. Emergency vehicle present (regardless of mode) — preempt everything.
        2. Manual override — honour the admin's request.
        3. Degraded — hold current phase.
        4. Automatic — let the scheduler pick the next phase.
    """
    # 1. Emergency ALWAYS wins, even if the junction is in MANUAL or DEGRADED
    #    mode. An emergency vehicle's life-safety priority beats every other
    #    concern. The transition planner still enforces YELLOW → ALL_RED
    #    downstream, so we never create conflicting GREEN states.
    if snap.emergency_dir:
        return Action(
            action=ACTION_EMERGENCY_PREEMPT,
            target_greens={snap.emergency_dir},
            reason=f"emergency vehicle from {snap.emergency_dir}",
        )

    # 2. Manual override — honour whatever direction the admin asked for.
    if snap.mode == "MANUAL" and snap.manual_override_dir:
        return Action(
            action=ACTION_MANUAL,
            target_greens={snap.manual_override_dir},
            reason=f"manual override on {snap.manual_override_dir}",
        )

    # 3. Degraded — never switch automatically. Wait for human/auto recovery.
    if snap.mode == "DEGRADED":
        return Action(action=ACTION_HOLD, reason="junction degraded; holding current phase")

    # 4. Automatic — let the scheduler decide.
    target = pick_next_phase(
        queues=snap.queues,
        current_phase=snap.current_phase,
        min_green_satisfied=snap.min_green_satisfied,
        starvation_threshold=snap.starvation_threshold,
    )
    if not target:
        return Action(action=ACTION_HOLD, reason="no queued traffic")

    if target == snap.current_phase:
        return Action(action=ACTION_HOLD, reason="current phase still optimal")

    return Action(
        action=ACTION_AUTOMATIC,
        target_greens=target,
        reason="scheduler picked new phase",
    )
