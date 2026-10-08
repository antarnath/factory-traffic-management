"""
Phase 2 domain-logic tests.

These are *pure* tests — no DB, no HTTP, no TestClient. They prove the
traffic brain works in isolation, satisfying spec §16 ("core traffic
logic should preferably be testable without HTTP/browser/MQTT/DB").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import (
    ACTION_AUTOMATIC,
    ACTION_EMERGENCY_PREEMPT,
    ACTION_HOLD,
    ACTION_MANUAL,
    DEFAULT_CONFLICTS,
    GREEN,
    RED,
    YELLOW,
    DirectionQueue,
    JunctionSnapshot,
    is_legal_signal_map,
    is_safe_transition,
    next_action,
    pick_next_phase,
    plan_transition,
    score_direction,
)
from app.services.safety import (
    assert_legal_signal_map,
    assert_safe_transition,
    conflicts_for,
)


# ============================================================
#   safety.py
# ============================================================

class TestSafety:
    """Spec §3 rules 1 + 2."""

    def test_parallel_greens_are_illegal(self):
        bad = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": GREEN, "WEST": RED}
        assert is_legal_signal_map(bad) is False

    def test_all_red_is_legal(self):
        all_red = {d: RED for d in ("NORTH", "SOUTH", "EAST", "WEST")}
        assert is_legal_signal_map(all_red) is True

    def test_perpendicular_pair_is_legal(self):
        # NS pair vs EW pair
        ok = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED}
        assert is_legal_signal_map(ok) is True

    def test_single_direction_green_is_legal(self):
        ok = {"NORTH": GREEN, "SOUTH": RED, "EAST": RED, "WEST": RED}
        assert is_legal_signal_map(ok) is True

    def test_cannot_skip_yellow_in_transition(self):
        # NS GREEN → EW GREEN without passing through YELLOW
        prev = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED}
        nxt  = {"NORTH": RED,   "SOUTH": RED,   "EAST": GREEN, "WEST": GREEN}
        assert is_safe_transition(prev, nxt) is False

    def test_safe_transition_through_yellow_passes(self):
        prev = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED}
        yel  = {"NORTH": YELLOW, "SOUTH": YELLOW, "EAST": RED, "WEST": RED}
        assert is_safe_transition(prev, yel) is True

    def test_safe_transition_all_red_passes(self):
        prev = {"NORTH": YELLOW, "SOUTH": YELLOW, "EAST": RED, "WEST": RED}
        all_red = {d: RED for d in ("NORTH", "SOUTH", "EAST", "WEST")}
        assert is_safe_transition(prev, all_red) is True

    def test_conflicts_for_helper(self):
        assert "EAST" in conflicts_for("NORTH")
        assert "SOUTH" not in conflicts_for("NORTH")
        assert "NORTH" in conflicts_for("EAST")
        assert "EAST" not in conflicts_for("EAST")  # a dir doesn't conflict with itself

    def test_assert_helpers_raise_on_violation(self):
        with pytest.raises(ValueError):
            assert_legal_signal_map({"NORTH": GREEN, "EAST": GREEN, "SOUTH": RED, "WEST": RED})
        with pytest.raises(ValueError):
            assert_safe_transition(
                {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED},
                {"NORTH": RED,   "SOUTH": RED,   "EAST": GREEN, "WEST": GREEN},
            )

    def test_default_conflicts_has_all_directions(self):
        for d in ("NORTH", "SOUTH", "EAST", "WEST"):
            assert d in DEFAULT_CONFLICTS
            assert len(DEFAULT_CONFLICTS[d]) == 2


# ============================================================
#   transitions.py
# ============================================================

class TestTransitions:
    """Spec §3 — GREEN → YELLOW → ALL_RED → GREEN."""

    def test_ns_to_ew_passes_through_yellow_and_all_red(self):
        current = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED}
        steps = plan_transition(current, {"EAST", "WEST"})
        assert len(steps) == 4
        # Step 0: current state
        assert steps[0] == current
        # Step 1: NS YELLOW, EW still RED
        assert steps[1]["NORTH"] == YELLOW
        assert steps[1]["SOUTH"] == YELLOW
        assert steps[1]["EAST"]  == RED
        assert steps[1]["WEST"]  == RED
        # Step 2: ALL RED
        assert all(s == RED for s in steps[2].values())
        # Step 3: EW GREEN
        assert steps[3]["EAST"] == GREEN
        assert steps[3]["WEST"] == GREEN
        assert steps[3]["NORTH"] == RED
        assert steps[3]["SOUTH"] == RED

    def test_plan_returns_single_step_when_already_at_target(self):
        current = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED}
        steps = plan_transition(current, {"NORTH", "SOUTH"})
        assert steps == [current]

    def test_plan_from_all_red_to_one_direction(self):
        current = {d: RED for d in ("NORTH", "SOUTH", "EAST", "WEST")}
        steps = plan_transition(current, {"NORTH"})
        # No current greens and no non-RED signals → skip the empty YELLOW
        # and ALL_RED steps entirely. The sequence jumps straight from
        # current (all red) to the target.
        assert steps[0] == current
        assert steps[-1]["NORTH"] == GREEN
        # The final state must be legal
        assert is_legal_signal_map(steps[-1])

    def test_unsafe_transition_raises(self):
        # Force an unsafe target by trying a custom (broken) conflict set
        broken_conflicts = {d: frozenset() for d in ("NORTH", "SOUTH", "EAST", "WEST")}
        # With no conflicts, going NS GREEN → EW GREEN is "safe" by rule 1,
        # but we also require that previous greens don't conflict with new
        # greens. Let's pick a real conflict and a target that violates it.
        current = {"NORTH": GREEN, "SOUTH": RED, "EAST": RED, "WEST": RED}
        # Trying to make both NORTH and EAST green while NORTH was already
        # green is illegal by rule 2 (NORTH's old GREEN conflicts with EAST).
        with pytest.raises(ValueError):
            plan_transition(current, {"NORTH", "EAST"})

    def test_all_intermediate_steps_are_legal(self):
        current = {"NORTH": GREEN, "SOUTH": GREEN, "EAST": RED, "WEST": RED}
        for a, b in zip(plan_transition(current, {"EAST"}), plan_transition(current, {"EAST"})[1:]):
            assert is_legal_signal_map(a)
            assert is_legal_signal_map(b)
            assert is_safe_transition(a, b)


# ============================================================
#   scheduler.py
# ============================================================

class TestScheduler:
    """Spec §5 — weighted phase selection with starvation protection."""

    def test_empty_queues_returns_none(self):
        assert pick_next_phase([], {"NORTH"}, True, 60) is None

    def test_no_flip_flop_when_min_green_not_satisfied(self):
        q = DirectionQueue("NORTH", {"TRUCK": 1}, None)
        result = pick_next_phase([q], {"NORTH"}, min_green_satisfied=False, starvation_threshold=60)
        assert result == {"NORTH"}

    def test_higher_priority_vehicle_wins(self):
        q_truck = DirectionQueue("NORTH", {"TRUCK": 5}, None)
        q_emp   = DirectionQueue("SOUTH", {"EMPLOYEE_VEHICLE": 100}, None)
        chosen = pick_next_phase([q_truck, q_emp], {"NORTH"},
                                 min_green_satisfied=True,
                                 starvation_threshold=10_000)
        # SOUTH has 100 employees × 5 = 500 priority vs NORTH's 5 trucks × 20 = 100
        assert chosen == {"SOUTH"}

    def test_emergency_always_wins(self):
        q_norm = DirectionQueue("NORTH", {"TRUCK": 100}, None)
        q_emrg = DirectionQueue("EAST",  {"EMERGENCY": 1}, None)
        chosen = pick_next_phase([q_norm, q_emrg], {"NORTH"},
                                 min_green_satisfied=True,
                                 starvation_threshold=10_000)
        assert chosen == {"EAST"}

    def test_starvation_forces_switch(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=120)
        q_old  = DirectionQueue("NORTH", {"TRUCK": 1}, old)
        q_new  = DirectionQueue("EAST",  {"TRUCK": 100}, datetime.now(timezone.utc))
        # NORTH has been waiting 120s (>60 threshold) → guaranteed win
        chosen = pick_next_phase([q_old, q_new], {"EAST"},
                                 min_green_satisfied=True,
                                 starvation_threshold=60)
        assert chosen == {"NORTH"}

    def test_holds_current_phase_when_optimal(self):
        # Best direction is already in the current phase; hold.
        q_a = DirectionQueue("NORTH", {"TRUCK": 5}, None)
        q_b = DirectionQueue("SOUTH", {"TRUCK": 5}, None)
        chosen = pick_next_phase([q_a, q_b], {"NORTH", "SOUTH"},
                                 min_green_satisfied=True,
                                 starvation_threshold=10_000)
        # Both have equal scores; the implementation holds the current phase.
        assert chosen == {"NORTH", "SOUTH"}

    def test_score_direction_higher_for_more_vehicles(self):
        q1 = DirectionQueue("NORTH", {"TRUCK": 1}, None)
        q2 = DirectionQueue("NORTH", {"TRUCK": 5}, None)
        assert score_direction(q2, 60) > score_direction(q1, 60)

    def test_score_direction_higher_for_older_queue(self):
        now = datetime.now(timezone.utc)
        q_old = DirectionQueue("NORTH", {"TRUCK": 1}, now - timedelta(seconds=30))
        q_new = DirectionQueue("NORTH", {"TRUCK": 1}, now)
        assert score_direction(q_old, 60) > score_direction(q_new, 60)


# ============================================================
#   state_machine.py
# ============================================================

class TestStateMachine:
    """Spec §6 + §7 — mode-aware decision logic."""

    def _snap(self, **overrides) -> JunctionSnapshot:
        defaults = dict(
            junction_id="A",
            mode="AUTOMATIC",
            current_phase={"NORTH"},
            signals={"NORTH": GREEN, "SOUTH": RED, "EAST": RED, "WEST": RED},
            queues=[],
            emergency_dir=None,
            manual_override_dir=None,
            min_green_satisfied=True,
            starvation_threshold=60,
        )
        defaults.update(overrides)
        return JunctionSnapshot(**defaults)

    def test_emergency_overrides_automatic(self):
        snap = self._snap(emergency_dir="EAST")
        action = next_action(snap)
        assert action.action == ACTION_EMERGENCY_PREEMPT
        assert action.target_greens == {"EAST"}

    def test_emergency_overrides_manual(self):
        # Even if an admin requested WEST, the emergency vehicle wins.
        snap = self._snap(
            mode="MANUAL", manual_override_dir="WEST", emergency_dir="EAST"
        )
        action = next_action(snap)
        assert action.action == ACTION_EMERGENCY_PREEMPT
        assert action.target_greens == {"EAST"}

    def test_manual_returns_target(self):
        snap = self._snap(mode="MANUAL", manual_override_dir="WEST")
        action = next_action(snap)
        assert action.action == ACTION_MANUAL
        assert action.target_greens == {"WEST"}

    def test_degraded_holds(self):
        snap = self._snap(mode="DEGRADED",
                          queues=[DirectionQueue("NORTH", {"TRUCK": 5}, None)])
        action = next_action(snap)
        assert action.action == ACTION_HOLD

    def test_automatic_picks_from_queues(self):
        snap = self._snap(
            queues=[DirectionQueue("EAST", {"TRUCK": 5}, None)],
            current_phase={"NORTH"},
        )
        action = next_action(snap)
        assert action.action == ACTION_AUTOMATIC
        assert action.target_greens == {"EAST"}

    def test_automatic_holds_when_no_queues(self):
        snap = self._snap(queues=[])
        action = next_action(snap)
        assert action.action == ACTION_HOLD

    def test_automatic_holds_when_current_still_optimal(self):
        snap = self._snap(
            queues=[DirectionQueue("NORTH", {"TRUCK": 1}, None)],
            current_phase={"NORTH"},
        )
        action = next_action(snap)
        assert action.action == ACTION_HOLD

    def test_automatic_respects_min_green(self):
        snap = self._snap(
            queues=[DirectionQueue("EAST", {"TRUCK": 5}, None)],
            current_phase={"NORTH"},
            min_green_satisfied=False,
        )
        action = next_action(snap)
        # Even though EAST has more trucks, we hold because min_green not met
        assert action.action == ACTION_HOLD
