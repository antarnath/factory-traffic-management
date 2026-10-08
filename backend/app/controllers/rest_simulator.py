"""
In-process controller simulator.

Behaves like a real physical controller for development/demos:
  - `send_command` returns immediately (no real network).
  - ONLINE / OFFLINE / DEGRADED state is tracked per junction.
  - ACKs come in via the REST `/api/controller-events` endpoint, which calls
    `deliver_ack`. We don't auto-ACK here because the test/demonstration
    flow needs to *see* the PENDING command first.

When MQTT is added later, this file becomes `mqtt_adapter.py` and implements
the same `ControllerAdapter` interface.
"""
from __future__ import annotations

import threading

from app.controllers.base import CommandResult, ControllerAdapter


class RestSimulator(ControllerAdapter):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._offline: set[str] = set()  # junction_ids currently offline

    def send_command(self, command_id: str, junction_id: str,
                     direction: str, requested_state: str) -> CommandResult:
        with self._lock:
            if junction_id in self._offline:
                return CommandResult(command_id, accepted=False,
                                     detail="controller offline")
        return CommandResult(command_id, accepted=True)

    def deliver_ack(self, command_id: str, actual_state: str,
                    status: str = "ACK") -> None:
        # In the simulator, the PendingCommand row in the database is the
        # source of truth; the controller doesn't need to track anything.
        return None

    def set_offline(self, junction_id: str, offline: bool) -> None:
        with self._lock:
            if offline:
                self._offline.add(junction_id)
            else:
                self._offline.discard(junction_id)

    def is_offline(self, junction_id: str) -> bool:
        with self._lock:
            return junction_id in self._offline


# Singleton — imported by the orchestrator and the maintenance API.
simulator = RestSimulator()
