"""
Enum types shared across models, schemas, and services.

Using str + enum.Enum so values are JSON-serialisable and Pydantic-friendly.
"""
import enum


class JunctionMode(str, enum.Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL    = "MANUAL"
    EMERGENCY = "EMERGENCY"
    DEGRADED  = "DEGRADED"


class SignalState(str, enum.Enum):
    RED    = "RED"
    YELLOW = "YELLOW"
    GREEN  = "GREEN"


class VehicleType(str, enum.Enum):
    FORKLIFT         = "FORKLIFT"
    TRUCK            = "TRUCK"
    EMPLOYEE_VEHICLE = "EMPLOYEE_VEHICLE"
    EMERGENCY        = "EMERGENCY"


class DeviceType(str, enum.Enum):
    SIGNAL     = "SIGNAL"
    SENSOR     = "SENSOR"
    CONTROLLER = "SIGNAL_CONTROLLER"


class DeviceStatus(str, enum.Enum):
    ONLINE   = "ONLINE"
    OFFLINE  = "OFFLINE"
    DEGRADED = "DEGRADED"
    WARNING  = "WARNING"
    UNKNOWN  = "UNKNOWN"


class CommandStatus(str, enum.Enum):
    PENDING  = "PENDING"
    ACK      = "ACK"
    TIMED_OUT = "TIMEOUT"
    FAILED   = "FAILED"
