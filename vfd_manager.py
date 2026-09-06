from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from .hy01d523b_vfd import HY01D523B

class VFDState(Enum):
    DISCONNECTED = "disconnected"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FAULT = "fault"

@dataclass
class VFDStatus:
    connected: bool = False
    state: VFDState = VFDState.DISCONNECTED
    running: bool = False
    reverse: bool = False
    frequency_hz: float = 0.0
    rpm: float = 0.0
    current_a: float = 0.0
    voltage_v: float = 0.0
    power_kw: float = 0.0
    dc_voltage_v: float = 0.0
    fault: bool = False
    fault_code: int = 0
    fault_text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

class VFDManager:
    def __init__(self, motor=None):
        self.motor = motor
        self.vfd: Optional[HY01D523B] = None
        self.serial_port = "COM3"
        self.slave_id = 4
        self.baudrate = 9600
        self.timeout = 0.25
        self.enabled = True
        self.armed = False
        self.target_frequency_hz = 0.0
        self.target_rpm = 0.0
        self.target_running = False
        self.target_reverse = False
        self.status = VFDStatus()

    def configure_connection(self, port, slave_id=4, baudrate=9600, timeout=0.25):
        self.serial_port = str(port)
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)

    def configure_motor(self, power_kw=None, voltage_v=None, rated_frequency_hz=None, rated_rpm=None, rated_current_a=None, poles=None, min_frequency_hz=None, max_frequency_hz=None, min_rpm=None, max_rpm=None):
        if self.motor is None:
            return
        values = {
            "power_kw": power_kw,
            "voltage_v": voltage_v,
            "rated_frequency_hz": rated_frequency_hz,
            "rated_rpm": rated_rpm,
            "rated_current_a": rated_current_a,
            "poles": poles,
            "min_frequency_hz": min_frequency_hz,
            "max_frequency_hz": max_frequency_hz,
            "min_rpm": min_rpm,
            "max_rpm": max_rpm,
        }
        for name, value in values.items():
            if value is not None and hasattr(self.motor, name):
                setattr(self.motor, name, value)

    def connect(self):
        self.disconnect()
        try:
            self.vfd = HY01D523B(
                serial_port=self.serial_port,
                slave_id=self.slave_id,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            if not self.vfd.connect():
                self._error(self.last_error() or "VFD connection failed.")
                self.vfd = None
                return False
            self.status = VFDStatus(
                connected=True,
                state=VFDState.READY,
            )
            return True
        except Exception as exc:
            self.vfd = None
            self._error(str(exc))
            return False

    def disconnect(self):
        if self.vfd is not None:
            try:
                self.vfd.disconnect()
            except Exception:
                pass
        self.vfd = None
        self.status.connected = False
        self.status.running = False
        self.status.state = VFDState.DISCONNECTED

    def is_connected(self):
        if self.vfd is None:
            return False
        try:
            return bool(self.vfd.is_connected())
        except Exception:
            return False

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            self.target_running = False

    def set_armed(self, armed):
        self.armed = bool(armed)
        if not self.armed:
            self.target_running = False

    def can_command(self):
        return self.enabled and self.armed and self.is_connected()

    def start(self):
        if not self.can_command():
            self._error("VFD is not enabled, armed and connected.")
            return False
        try:
            result = self.vfd.reverse_run() if self.target_reverse else self.vfd.run()
            if result:
                self.target_running = True
                self.status.running = True
                self.status.reverse = self.target_reverse
                self.status.state = VFDState.RUNNING
            else:
                self._error(self.last_error() or "VFD start command failed.")
            return bool(result)
        except Exception as exc:
            self._error(str(exc))
            return False

    def stop(self):
        if not self.is_connected():
            self._error("VFD is not connected.")
            return False
        try:
            result = self.vfd.stop()
            if result:
                self.target_running = False
                self.status.running = False
                self.status.state = VFDState.STOPPED
            else:
                self._error(self.last_error() or "VFD stop command failed.")
            return bool(result)
        except Exception as exc:
            self._error(str(exc))
            return False

    def emergency_stop(self):
        return self.stop()

    def set_frequency(self, frequency_hz):
        frequency_hz = float(frequency_hz)
        minimum = self._motor_value("min_frequency_hz", 0.0)
        maximum = self._motor_value("max_frequency_hz", 400.0)
        frequency_hz = max(minimum, min(frequency_hz, maximum))
        self.target_frequency_hz = frequency_hz
        rated_frequency = self._motor_value("rated_frequency_hz", 400.0)
        rated_rpm = self._motor_value("rated_rpm", 24000.0)
        if rated_frequency > 0:
            self.target_rpm = frequency_hz / rated_frequency * rated_rpm
        if not self.can_command():
            self._error("VFD is not enabled, armed and connected.")
            return False
        try:
            result = self.vfd.set_frequency(frequency_hz)
            if result:
                self.status.frequency_hz = frequency_hz
                self.status.rpm = self.target_rpm
            else:
                self._error(self.last_error() or "VFD frequency command failed.")
            return bool(result)
        except Exception as exc:
            self._error(str(exc))
            return False

    def set_speed(self, rpm):
        rpm = float(rpm)
        minimum = self._motor_value("min_rpm", 0.0)
        maximum = self._motor_value("max_rpm", 24000.0)
        rpm = max(minimum, min(rpm, maximum))
        rated_rpm = self._motor_value("rated_rpm", 24000.0)
        rated_frequency = self._motor_value("rated_frequency_hz", 400.0)
        if rated_rpm <= 0:
            self._error("Motor rated RPM must be greater than zero.")
            return False
        self.target_rpm = rpm
        return self.set_frequency(rpm / rated_rpm * rated_frequency)

    def set_direction(self, reverse):
        self.target_reverse = bool(reverse)
        if not self.can_command():
            self._error("VFD is not enabled, armed and connected.")
            return False
        try:
            result = self.vfd.reverse_run() if self.target_reverse else self.vfd.forward()
            if result:
                self.status.reverse = self.target_reverse
                self.status.running = True
                self.status.state = VFDState.RUNNING
                self.target_running = True
            else:
                self._error(self.last_error() or "VFD direction command failed.")
            return bool(result)
        except Exception as exc:
            self._error(str(exc))
            return False

    def update_status(self):
        if not self.is_connected():
            self.status.connected = False
            self.status.running = False
            self.status.state = VFDState.DISCONNECTED
            return self.status
        try:
            raw = self.vfd.get_local_status()
            self.status.connected = bool(raw.get("connected", True))
            self.status.running = bool(raw.get("running", False))
            self.status.reverse = bool(raw.get("reverse", False))
            self.status.frequency_hz = float(raw.get("frequency", self.target_frequency_hz))
            self.status.rpm = self._frequency_to_rpm(self.status.frequency_hz)
            self.status.fault = bool(raw.get("fault", False))
            self.status.fault_code = int(raw.get("fault_code", 0))
            self.status.fault_text = str(raw.get("error", ""))
            self.status.raw = raw
            if not self.status.connected:
                self.status.state = VFDState.DISCONNECTED
            elif self.status.fault:
                self.status.state = VFDState.FAULT
            elif self.status.running:
                self.status.state = VFDState.RUNNING
            else:
                self.status.state = VFDState.READY
        except Exception as exc:
            self._error(str(exc))
        return self.status

    def get_status(self):
        return self.status

    def read_parameter(self, parameter):
        try:
            parameter = self._validate_parameter(parameter)
        except (TypeError, ValueError) as exc:
            self._error(str(exc))
            return None
        if not self.is_connected():
            self._error("VFD is not connected.")
            return None
        try:
            return self.vfd.read_parameter(parameter)
        except Exception as exc:
            self._error(str(exc))
            return None

    def write_parameter(self, parameter, value):
        try:
            parameter = self._validate_parameter(parameter)
            value = int(value)
        except (TypeError, ValueError) as exc:
            self._error(str(exc))
            return False
        if not 0 <= value <= 0xFFFF:
            self._error("Parameter value must be between 0 and 65535.")
            return False
        if not self.is_connected():
            self._error("VFD is not connected.")
            return False
        try:
            result = self.vfd.write_parameter(parameter, value)
            if not result:
                self._error(self.last_error() or "VFD parameter write failed.")
            return bool(result)
        except Exception as exc:
            self._error(str(exc))
            return False

    def read_pd(self, parameter):
        return self.read_parameter(parameter)

    def write_pd(self, parameter, value):
        return self.write_parameter(parameter, value)

    def _validate_parameter(self, parameter):
        parameter = int(parameter)
        if not 0 <= parameter <= 182:
            raise ValueError("HY01D523B parameter must be PD000 through PD182.")
        return parameter

    def last_error(self):
        if self.vfd is not None:
            return str(getattr(self.vfd, "last_error", ""))
        return self.status.fault_text

    def _error(self, message):
        self.status.fault = True
        self.status.fault_text = str(message)

    def _motor_value(self, name, default):
        if self.motor is None:
            return float(default)
        try:
            return float(getattr(self.motor, name, default))
        except (TypeError, ValueError):
            return float(default)

    def _frequency_to_rpm(self, frequency_hz):
        rated_frequency = self._motor_value("rated_frequency_hz", 400.0)
        rated_rpm = self._motor_value("rated_rpm", 24000.0)
        if rated_frequency <= 0:
            return 0.0
        return float(frequency_hz) / rated_frequency * rated_rpm
