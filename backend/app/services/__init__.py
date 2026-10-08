"""
Traffic domain services.

Pure-Python modules that encode the safety rules, transition planner,
phase scheduler, junction state machine, queue aggregation, and
per-junction row locking. No HTTP, no FastAPI imports in here — the
domain is decoupled from the transport.

Re-exports the most commonly used symbols for convenience.
"""
from app.services.concurrency import junction_lock
from app.services.queue import build_direction_queues, queue_size_per_direction
from app.services.safety import (
    ALL_VALID_STATES,
    DEFAULT_CONFLICTS,
    GREEN,
    RED,
    YELLOW,
    assert_legal_signal_map,
    assert_safe_transition,
    conflicts_for,
    is_legal_signal_map,
    is_safe_transition,
)
from app.services.scheduler import (
    COEF_PRIORITY,
    COEF_SIZE,
    COEF_WAITING,
    STARVATION_BONUS,
    VEHICLE_PRIORITY_WEIGHT,
    DirectionQueue,
    pick_next_phase,
    score_direction,
)
from app.services.state_machine import (
    ACTION_AUTOMATIC,
    ACTION_DEGRADED,
    ACTION_EMERGENCY_PREEMPT,
    ACTION_HOLD,
    ACTION_MANUAL,
    Action,
    JunctionSnapshot,
    next_action,
)
from app.services.transitions import (
    ALL_RED_DURATION_DEFAULT,
    YELLOW_DURATION_DEFAULT,
    first_step,
    plan_transition,
    transition_durations,
)

__all__ = [
    # safety
    "ALL_VALID_STATES", "DEFAULT_CONFLICTS", "GREEN", "RED", "YELLOW",
    "assert_legal_signal_map", "assert_safe_transition",
    "conflicts_for", "is_legal_signal_map", "is_safe_transition",
    # scheduler
    "COEF_PRIORITY", "COEF_SIZE", "COEF_WAITING", "STARVATION_BONUS",
    "VEHICLE_PRIORITY_WEIGHT", "DirectionQueue",
    "pick_next_phase", "score_direction",
    # transitions
    "ALL_RED_DURATION_DEFAULT", "YELLOW_DURATION_DEFAULT",
    "first_step", "plan_transition", "transition_durations",
    # state machine
    "ACTION_AUTOMATIC", "ACTION_DEGRADED", "ACTION_EMERGENCY_PREEMPT",
    "ACTION_HOLD", "ACTION_MANUAL", "Action", "JunctionSnapshot", "next_action",
    # queue + concurrency
    "build_direction_queues", "queue_size_per_direction", "junction_lock",
]
