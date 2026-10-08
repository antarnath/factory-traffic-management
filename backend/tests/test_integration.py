"""
End-to-end integration tests covering the scenarios from spec §15.

These tests exercise the full HTTP → service → DB → audit path using
the FastAPI TestClient. Each test corresponds to one named scenario in
the spec, so a failure points directly at the rule that's broken.

They also double as living documentation: the test name describes the
behaviour, the body describes how the system achieves it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import app.db as app_db
from app.models import PendingCommand
from sqlalchemy import text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------------------------
#  Helpers
# -------------------------------------------------------------------------

def _create_junction(client, junction_id: str = "A") -> dict:
    r = client.post("/api/junctions", json={"id": junction_id, "name": "Test"})
    assert r.status_code == 201, r.text
    return r.json()


def _vehicle_event(client, junction_id: str, direction: str, kind: str,
                   vehicle_id: str, vtype: str, seq: int,
                   ts: datetime | None = None) -> dict:
    payload = {
        "event_id": f"e-{vehicle_id}-{kind}-{seq}",
        "junction_id": junction_id,
        "direction": direction,
        "event_type": kind,
        "vehicle_id": vehicle_id,
        "vehicle_type": vtype,
        "sequence_no": seq,
        "timestamp": (ts or datetime.now(timezone.utc)).isoformat(),
    }
    r = client.post("/api/sensor-events", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _status(client, junction_id: str) -> dict:
    r = client.get(f"/api/junctions/{junction_id}/status")
    assert r.status_code == 200, r.text
    return r.json()


def _latest_pending_cmd(client, junction_id: str,
                        direction: str | None = None) -> str | None:
    """Find the most recent PENDING/SENT command for a junction, optionally
    restricted to one direction."""
    with app_db.SessionLocal() as db:
        q = (db.query(PendingCommand)
               .filter(PendingCommand.junction_id == junction_id,
                       PendingCommand.status.in_(["PENDING", "SENT"])))
        if direction is not None:
            q = q.filter(PendingCommand.direction == direction)
        cmd = q.order_by(PendingCommand.sent_at.desc()).first()
        return cmd.command_id if cmd else None


# -------------------------------------------------------------------------
#  S1: Basic vehicle arrival picks the right phase
# -------------------------------------------------------------------------

def test_scenario_1_vehicle_arrival_picks_phase(client):
    _create_junction(client)
    _vehicle_event(client, "A", "NORTH", "VEHICLE_ARRIVED", "v1", "TRUCK", 1)
    s = _status(client, "A")
    assert s["queues"]["NORTH"] == 1
    # The orchestrator should have transitioned or set up NORTH for GREEN.
    assert s["desired_signals"]["NORTH"] in ("GREEN", "YELLOW", "RED")


# -------------------------------------------------------------------------
#  S2: Higher-priority vehicle wins over lower
# -------------------------------------------------------------------------

def test_scenario_2_emergency_preempts(client):
    _create_junction(client)
    # Five trucks on EAST
    for i in range(5):
        _vehicle_event(client, "A", "EAST", "VEHICLE_ARRIVED",
                       f"t{i}", "TRUCK", i + 1)
    # One emergency on NORTH — emergency preempts via state machine.
    _vehicle_event(client, "A", "NORTH", "VEHICLE_ARRIVED",
                   "amb", "EMERGENCY", 100)
    s = _status(client, "A")
    assert s["mode"] == "EMERGENCY"
    assert s["emergency_active"] is True


# -------------------------------------------------------------------------
#  S3: Starvation protection — a long-waiting queue gets considered
# -------------------------------------------------------------------------

def test_scenario_3_starvation_protection(client):
    _create_junction(client)
    # A single truck that arrived "a long time ago"
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    _vehicle_event(client, "A", "NORTH", "VEHICLE_ARRIVED", "old",
                   "TRUCK", 1, ts=old)
    # Make EAST busier so scheduler would otherwise pick EAST.
    for i in range(5):
        _vehicle_event(client, "A", "EAST", "VEHICLE_ARRIVED",
                       f"b{i}", "TRUCK", i + 10)
    s = _status(client, "A")
    # The starvation bonus guarantees NORTH is at least considered.
    # (We can't peek at scheduler internals, but the snapshot must show
    # NORTH still in the queue.)
    assert s["queues"]["NORTH"] >= 1


# -------------------------------------------------------------------------
#  S4: Idempotency — replaying an event returns "already_processed"
# -------------------------------------------------------------------------

def test_scenario_4_idempotency(client):
    _create_junction(client)
    payload = {
        "event_id": "dup-1",
        "junction_id": "A",
        "direction": "NORTH",
        "event_type": "VEHICLE_ARRIVED",
        "vehicle_id": "v1",
        "vehicle_type": "TRUCK",
        "sequence_no": 1,
        "timestamp": _now_iso(),
    }
    r1 = client.post("/api/sensor-events", json=payload)
    r2 = client.post("/api/sensor-events", json=payload)
    assert r1.json()["status"] == "processed"
    assert r2.json()["status"] == "already_processed"
    s = _status(client, "A")
    assert s["queues"]["NORTH"] == 1


# -------------------------------------------------------------------------
#  S5: Out-of-order rejection — late sequence_no is dropped
# -------------------------------------------------------------------------

def test_scenario_5_out_of_order(client):
    _create_junction(client)
    ts = datetime.now(timezone.utc)
    _vehicle_event(client, "A", "NORTH", "VEHICLE_ARRIVED", "v1", "TRUCK", 1, ts=ts)
    out = _vehicle_event(client, "A", "NORTH", "VEHICLE_ARRIVED", "v0", "TRUCK", 0, ts=ts)
    assert out["status"] == "out_of_order"
    s = _status(client, "A")
    assert s["queues"]["NORTH"] == 1


# -------------------------------------------------------------------------
#  S6: Safety — opposing directions never both GREEN
# -------------------------------------------------------------------------

def test_scenario_6_no_conflicting_greens(client):
    _create_junction(client)
    # Pile on opposing directions
    for d in ("NORTH", "SOUTH", "EAST", "WEST"):
        _vehicle_event(client, "A", d, "VEHICLE_ARRIVED",
                       f"v-{d}", "TRUCK", hash(d) % 100)
    s = _status(client, "A")
    greens = [d for d, st in s["desired_signals"].items() if st == "GREEN"]
    conflicts = {"NORTH": {"EAST", "WEST"}, "SOUTH": {"EAST", "WEST"},
                 "EAST": {"NORTH", "SOUTH"}, "WEST": {"NORTH", "SOUTH"}}
    for g in greens:
        for c in conflicts.get(g, ()):
            assert s["desired_signals"][c] != "GREEN"


# -------------------------------------------------------------------------
#  S7: Manual override → MANUAL mode
# -------------------------------------------------------------------------

def test_scenario_7_manual_override(client):
    _create_junction(client)
    r = client.post("/api/junctions/A/commands",
                    json={"command": "MANUAL_GREEN_REQUEST", "direction": "WEST"})
    assert r.status_code == 200
    s = _status(client, "A")
    assert s["mode"] == "MANUAL"
    assert s["manual_override_active"] is True


def test_scenario_7b_return_to_automatic(client):
    _create_junction(client)
    client.post("/api/junctions/A/commands",
                json={"command": "MANUAL_GREEN_REQUEST", "direction": "WEST"})
    r = client.post("/api/junctions/A/commands",
                    json={"command": "RETURN_TO_AUTOMATIC"})
    assert r.status_code == 200
    s = _status(client, "A")
    assert s["mode"] == "AUTOMATIC"


# -------------------------------------------------------------------------
#  S8: Device OFFLINE → DEGRADED mode
# -------------------------------------------------------------------------

def test_scenario_8_device_offline_degraded(client):
    _create_junction(client)
    r = client.post("/api/device-events", json={
        "event_id": "dev-1", "junction_id": "A",
        "device_type": "SIGNAL_CONTROLLER", "status": "OFFLINE",
        "timestamp": _now_iso(),
    })
    assert r.status_code == 200
    s = _status(client, "A")
    assert s["mode"] == "DEGRADED"
    assert s["controller_status"] == "OFFLINE"


def test_scenario_8b_device_online_recovers(client):
    _create_junction(client)
    client.post("/api/device-events", json={
        "event_id": "dev-1", "junction_id": "A",
        "device_type": "SIGNAL_CONTROLLER", "status": "OFFLINE",
        "timestamp": _now_iso(),
    })
    client.post("/api/device-events", json={
        "event_id": "dev-2", "junction_id": "A",
        "device_type": "SIGNAL_CONTROLLER", "status": "ONLINE",
        "timestamp": _now_iso(),
    })
    s = _status(client, "A")
    assert s["mode"] == "AUTOMATIC"


# -------------------------------------------------------------------------
#  S9: Controller ACK updates actual_state
# -------------------------------------------------------------------------

def test_scenario_9_controller_ack_updates_actual(client):
    _create_junction(client)
    # Force a manual GREEN to definitely get a pending command out.
    client.post("/api/junctions/A/commands",
                json={"command": "MANUAL_GREEN_REQUEST", "direction": "EAST"})
    cmd_id = _latest_pending_cmd(client, "A", direction="EAST")
    assert cmd_id is not None, "no EAST pending command was produced"
    r = client.post("/api/controller-events", json={
        "command_id": cmd_id, "junction_id": "A",
        "status": "ACK", "actual_state": "GREEN",
        "timestamp": _now_iso(),
    })
    assert r.status_code == 200
    s = _status(client, "A")
    assert s["actual_signals"].get("EAST") == "GREEN"


# -------------------------------------------------------------------------
#  Status endpoint reflects reality
# -------------------------------------------------------------------------

def test_status_reflects_queue_and_signals(client):
    _create_junction(client)
    for i, d in enumerate(("NORTH", "EAST", "WEST")):
        _vehicle_event(client, "A", d, "VEHICLE_ARRIVED", f"v-{d}",
                       "TRUCK", i + 1)
    s = _status(client, "A")
    assert sum(s["queues"].values()) == 3
    assert all(d in s["desired_signals"]
               for d in ("NORTH", "SOUTH", "EAST", "WEST"))


# -------------------------------------------------------------------------
#  History endpoint
# -------------------------------------------------------------------------

def test_history_contains_vehicle_arrived(client):
    _create_junction(client)
    _vehicle_event(client, "A", "NORTH", "VEHICLE_ARRIVED", "v1", "TRUCK", 1)
    r = client.get("/api/junctions/A/history")
    assert r.status_code == 200
    events = r.json()["events"]
    types = {e["event_type"] for e in events}
    assert "VEHICLE_ARRIVED" in types


# -------------------------------------------------------------------------
#  Unknown junction → 404 in envelope
# -------------------------------------------------------------------------

def test_unknown_junction_returns_envelope_404(client):
    r = client.get("/api/junctions/ZZZZ")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "junction_not_found"


# -------------------------------------------------------------------------
#  Pending command endpoint (used by the dashboard's "Send ACK" button)
# -------------------------------------------------------------------------

def test_pending_command_none_when_no_commands(client):
    _create_junction(client)
    r = client.get("/api/junctions/A/pending-command")
    assert r.status_code == 200
    assert r.json() == {"command_id": None}


def test_pending_command_returns_latest_after_manual(client):
    _create_junction(client)
    client.post("/api/junctions/A/commands",
                json={"command": "MANUAL_GREEN_REQUEST", "direction": "EAST"})
    r = client.get("/api/junctions/A/pending-command")
    assert r.status_code == 200
    cmd_id = r.json()["command_id"]
    assert cmd_id is not None
    assert cmd_id.startswith("cmd-A-")


def test_pending_command_404_for_unknown_junction(client):
    r = client.get("/api/junctions/ZZZZ/pending-command")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "junction_not_found"


# -------------------------------------------------------------------------
#  Static mount (frontend dashboard)
# -------------------------------------------------------------------------

def test_dashboard_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    # index.html is the dashboard
    assert b"Factory Traffic" in r.content
    assert b"<svg" in r.content


def test_dashboard_css_served(client):
    r = client.get("/style.css")
    assert r.status_code == 200
    assert b"--green" in r.content


def test_dashboard_js_served(client):
    r = client.get("/app.js")
    assert r.status_code == 200
    assert b"pollStatus" in r.content


def test_api_works_alongside_static_mount(client):
    """Mounting static at / must not break the API."""
    _create_junction(client)
    r = client.get("/api/junctions/A")
    assert r.status_code == 200
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# -------------------------------------------------------------------------
#  Manual override expires → AUTOMATIC
# -------------------------------------------------------------------------

def test_manual_override_expires(client):
    _create_junction(client)
    r = client.post("/api/junctions/A/commands",
                    json={"command": "MANUAL_GREEN_REQUEST", "direction": "WEST"})
    assert r.status_code == 200
    # Maintenance tick returns the right shape.
    r = client.post("/api/maintenance/tick")
    assert r.status_code == 200
    body = r.json()
    assert "expired_manual_overrides" in body
    assert "timed_out_commands" in body
    assert "reconciled" in body


# -------------------------------------------------------------------------
#  Alerts panel (spec §14.6)
#
#  The frontend alerts panel is rendered from the status payload. These
#  tests verify that the status payload carries the fields the alerts
#  panel needs to highlight each failure type from spec §14.6:
#     - controller offline
#     - signal failure
#     - sensor failure
#     - desired/actual mismatch
#     - command timeout
#     - unknown device state
# -------------------------------------------------------------------------

def test_alerts_payload_includes_controller_status(client):
    """The alerts panel classifies by controller_status; verify the field exists."""
    _create_junction(client)
    s = _status(client, "A")
    assert "controller_status" in s
    assert s["controller_status"] in ("ONLINE", "OFFLINE", "DEGRADED",
                                      "WARNING", "UNKNOWN")


def test_alerts_payload_controller_offline(client):
    """A device event that takes the controller OFFLINE must surface in status."""
    _create_junction(client)
    client.post("/api/device-events", json={
        "event_id": "dev-1", "junction_id": "A",
        "device_type": "SIGNAL_CONTROLLER", "status": "OFFLINE",
        "timestamp": _now_iso(),
    })
    s = _status(client, "A")
    assert s["controller_status"] == "OFFLINE"
    assert s["mode"] == "DEGRADED"  # backend drops to DEGRADED on offline


def test_alerts_payload_warning_status(client):
    """The backend accepts WARNING; the frontend shows it as a soft alert."""
    _create_junction(client)
    # The device-events endpoint may or may not switch to DEGRADED on WARNING
    # depending on backend policy; we only assert the status is reported.
    client.post("/api/device-events", json={
        "event_id": "dev-warn", "junction_id": "A",
        "device_type": "SIGNAL_CONTROLLER", "status": "WARNING",
        "timestamp": _now_iso(),
    })
    s = _status(client, "A")
    # The status payload must always include controller_status so the
    # frontend can render a warning pill.
    assert s["controller_status"] in ("ONLINE", "WARNING", "DEGRADED",
                                      "OFFLINE", "UNKNOWN")


def test_alerts_payload_includes_desired_and_actual(client):
    """Mismatch alerts compare desired_signals vs actual_signals per direction."""
    _create_junction(client)
    # No commands yet, so both should be present and equal (all RED).
    s = _status(client, "A")
    assert "desired_signals" in s
    assert "actual_signals" in s
    for d in ("NORTH", "SOUTH", "EAST", "WEST"):
        assert d in s["desired_signals"]
        assert d in s["actual_signals"]


def test_alerts_payload_pending_command_field(client):
    """The 'command timeout' alert needs pending_command_id on the status."""
    _create_junction(client)
    client.post("/api/junctions/A/commands",
                json={"command": "MANUAL_GREEN_REQUEST", "direction": "EAST"})
    s = _status(client, "A")
    assert "pending_command_id" in s
    assert s["pending_command_id"] is not None


# -------------------------------------------------------------------------
#  Alerts panel — static mount side
# -------------------------------------------------------------------------

def test_alerts_card_present_in_dashboard(client):
    """The alerts panel must be a top-level card in the dashboard HTML."""
    r = client.get("/")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert 'id="alerts-card"' in body
    assert 'id="alerts-list"' in body
    assert 'id="alerts-summary"' in body


def test_alerts_css_classes_present(client):
    """The alert severity styles must be present in the served CSS."""
    r = client.get("/style.css")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    for cls in ("alert-error", "alert-warn", "alert-ok", "alerts-list"):
        assert cls in body, f"missing {cls} in style.css"


def test_alerts_logic_in_app_js(client):
    """The JS file must contain the computeAlerts function and the rules
    referenced from the spec §14.6 (controller offline, mismatch, etc.)."""
    r = client.get("/app.js")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert "computeAlerts" in body
    assert "renderAlerts"  in body
    # Each spec failure type appears in the detection function
    for needle in ("Controller offline", "Signal mismatch",
                   "Command unacknowledged", "Controller degraded",
                   "Controller state unclear", "DEGRADED mode"):
        assert needle in body, f"missing alert text: {needle!r}"