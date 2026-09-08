from dataclasses import dataclass
from enum import Enum


class VFDState(Enum):
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAULT = "fault"


@dataclass
class VFDStatus:
    # Communication
    connected: bool = False
    communication_ok: bool = False

    # State
    state: VFDState = VFDState.DISCONNECTED

    # Commanded values
    commanded_running: bool = False
    commanded_reverse: bool = False
    commanded_frequency_hz: float = 0.0

    # Actual VFD values
    actual_frequency_hz: float = 0.0
    actual_rpm: float = 0.0
    actual_current_a: float = 0.0

    dc_voltage_v: float = 0.0
    ac_voltage_v: float = 0.0
    temperature_c: float = 0.0

    # Fault
    fault: bool = False
    fault_code: int | None = None
    fault_text: str = ""

    # Diagnostics
    consecutive_failures: int = 0
