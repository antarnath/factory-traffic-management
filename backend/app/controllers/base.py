"""
Abstract controller adapter.

A "controller" in this project is the physical (or simulated) box that
actually drives the LED panels and reports their state back. Spec §13 says
we should be able to swap REST for MQTT without rewriting the core, so
we hide both behind this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of sending one command to a controller."""

    command_id: str
    accepted: bool
    detail: str = ""


class ControllerAdapter(ABC):
    """Interface every controller adapter (REST, MQTT, real hardware) implements."""

    @abstractmethod
    def send_command(self, command_id: str, junction_id: str,
                     direction: str, requested_state: str) -> CommandResult: ...

    @abstractmethod
    def deliver_ack(self, command_id: str, actual_state: str,
                    status: str = "ACK") -> None: ...

    @abstractmethod
    def set_offline(self, junction_id: str, offline: bool) -> None: ...

    @abstractmethod
    def is_offline(self, junction_id: str) -> bool: ...
