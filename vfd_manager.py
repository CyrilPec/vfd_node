from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
try:
    from .hy01d523b_vfd import HY01D523B
except ImportError:
    from hy01d523b_vfd import HY01D523B
try:
    import serial
except ImportError:
    serial = None
class VFDState(Enum):
    UNKNOWN = "unknown"
    DISCONNECTED = "disconnected"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FAULT = "fault"
    EMERGENCY_STOP = "emergency_stop"
class VFDDirection(Enum):
    FORWARD = "forward"
    REVERSE = "reverse"
@dataclass
class VFDStatus:
    connected: bool = False
    state: VFDState = VFDState.DISCONNECTED
    running: bool = False
    direction: VFDDirection = VFDDirection.FORWARD
    frequency_hz: float = 0.0
    rpm: float = 0.0
    current_a: float = 0.0
    voltage_v: float = 0.0
    power_kw: float = 0.0
    dc_voltage_v: float = 0.0
    fault: bool = False
    fault_code: int = 0
    fault_text: str = ""
    warning: bool = False
    warning_code: int = 0
    warning_text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
@dataclass
class VFDMotorConfig:
    power_kw: float = 1.5
    voltage_v: float = 220.0
    rated_frequency_hz: float = 400.0
    rated_rpm: float = 24000.0
    rated_current_a: float = 0.0
    poles: int = 2
    min_frequency_hz: float = 0.0
    max_frequency_hz: float = 400.0
    min_rpm: float = 0.0
    max_rpm: float = 24000.0
class VFDDriver:
    name = "Generic VFD Driver"
    def connect(self) -> bool:
        raise NotImplementedError
    def disconnect(self) -> None:
        raise NotImplementedError
    def is_connected(self) -> bool:
        return False
    def start(self) -> bool:
        raise NotImplementedError
    def stop(self) -> bool:
        raise NotImplementedError
    def emergency_stop(self) -> bool:
        return self.stop()
    def reset_fault(self) -> bool:
        raise NotImplementedError
    def set_frequency(self, frequency_hz: float) -> bool:
        raise NotImplementedError
    def set_speed(self, rpm: float) -> bool:
        raise NotImplementedError
    def set_direction(self, direction: VFDDirection) -> bool:
        raise NotImplementedError
    def get_status(self) -> VFDStatus:
        raise NotImplementedError
    def read_parameter(self, parameter: int):
        raise NotImplementedError
    def write_parameter(self, parameter: int, value: int) -> bool:
        raise NotImplementedError
class HY01D523BAdapter(VFDDriver):
    name = "HY01D523B"
    def __init__(self, port: str, slave_id: int = 4, baudrate: int = 9600, timeout: float = 0.25):
        self.port = str(port)
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.serial = None
        self.driver = None
        self.last_error = ""
    def connect(self) -> bool:
        if serial is None:
            self.last_error = "pyserial is not installed."
            return False
        try:
            if self.serial is None:
                self.serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                    rtscts=False,
                    dsrdtr=False,
                    xonxoff=False,
                )
            elif not self.serial.is_open:
                self.serial.open()
            self.driver = HY01D523B(
                serial_port=self.serial,
                slave_id=self.slave_id,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            if not self.driver.connect():
                self.last_error = getattr(self.driver, "last_error", "Connection failed.")
                return False
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.driver = None
            return False
    def disconnect(self) -> None:
        try:
            if self.driver is not None:
                self.driver.disconnect()
        except Exception:
            pass
        self.driver = None
        try:
            if self.serial is not None and self.serial.is_open:
                self.serial.close()
        except Exception:
            pass
    def is_connected(self) -> bool:
        if self.driver is None:
            return False
        try:
            return bool(self.driver.is_connected())
        except Exception:
            return False
    def start(self) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.reverse_run() if self.driver.reverse else self.driver.run())
            if not result:
                self.last_error = getattr(self.driver, "last_error", "Start failed.")
            return result
        except Exception as exc:
            self.last_error = str(exc)
            return False
    def stop(self) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.stop())
            if not result:
                self.last_error = getattr(self.driver, "last_error", "Stop failed.")
            return result
        except Exception as exc:
            self.last_error = str(exc)
            return False
    def emergency_stop(self) -> bool:
        return self.stop()
    def reset_fault(self) -> bool:
        self.last_error = "HY01D523B fault reset is not implemented."
        return False
    def set_frequency(self, frequency_hz: float) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.set_frequency(float(frequency_hz)))
            if not result:
                self.last_error = getattr(self.driver, "last_error", "Frequency command failed.")
            return result
        except Exception as exc:
            self.last_error = str(exc)
            return False
    def set_speed(self, rpm: float) -> bool:
        self.last_error = "RPM control is handled by VFDManager."
        return False
    def set_direction(self, direction: VFDDirection) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False
        try:
            if direction == VFDDirection.REVERSE:
                result = bool(self.driver.reverse_run())
            else:
                result = bool(self.driver.forward())
            if not result:
                self.last_error = getattr(self.driver, "last_error", "Direction command failed.")
            return result
        except Exception as exc:
            self.last_error = str(exc)
            return False
    def get_status(self) -> VFDStatus:
        if self.driver is None:
            return VFDStatus()
        try:
            raw = self.driver.get_local_status()
            connected = bool(raw.get("connected", False))
            running = bool(raw.get("running", False))
            reverse = bool(raw.get("reverse", False))
            frequency = float(raw.get("frequency", 0.0))
            fault = bool(raw.get("fault", False))
            fault_code = int(raw.get("fault_code", 0))
            error = str(raw.get("error", ""))
            if not connected:
                state = VFDState.DISCONNECTED
            elif fault:
                state = VFDState.FAULT
            elif running:
                state = VFDState.RUNNING
            else:
                state = VFDState.READY
            return VFDStatus(
                connected=connected,
                state=state,
                running=running,
                direction=VFDDirection.REVERSE if reverse else VFDDirection.FORWARD,
                frequency_hz=frequency,
                fault=fault,
                fault_code=fault_code,
                fault_text=error,
                raw=raw,
            )
        except Exception as exc:
            self.last_error = str(exc)
            return VFDStatus(
                connected=False,
                state=VFDState.DISCONNECTED,
                fault_text=str(exc),
            )
    def read_parameter(self, parameter: int):
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return None
        try:
            return self.driver.read_parameter(int(parameter))
        except Exception as exc:
            self.last_error = str(exc)
            return None
    def write_parameter(self, parameter: int, value: int) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.write_parameter(int(parameter), int(value)))
            if not result:
                self.last_error = getattr(self.driver, "last_error", "Parameter write failed.")
            return result
        except Exception as exc:
            self.last_error = str(exc)
            return False
class VFDManager:
    def __init__(self, driver: Optional[VFDDriver] = None, motor: Optional[VFDMotorConfig] = None):
        self.driver = driver
        self.motor = motor or VFDMotorConfig()
        self.status = VFDStatus()
        self.enabled = True
        self.armed = False
        self.serial_port = "COM3"
        self.slave_id = 4
        self.baudrate = 9600
        self.timeout = 0.25
        self.target_frequency_hz = 0.0
        self.target_rpm = 0.0
        self.target_running = False
        self.target_direction = VFDDirection.FORWARD
    def configure_connection(self, port: str, slave_id: int = 4, baudrate: int = 9600, timeout: float = 0.25) -> None:
        port = str(port)
        slave_id = int(slave_id)
        baudrate = int(baudrate)
        timeout = float(timeout)
        changed = (
            port != self.serial_port
            or slave_id != self.slave_id
            or baudrate != self.baudrate
            or timeout != self.timeout
        )
        if changed and self.driver is not None:
            try:
                self.driver.disconnect()
            except Exception:
                pass
            self.driver = None
        self.serial_port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.timeout = timeout
    def create_hy01d523b_driver(self) -> VFDDriver:
        self.driver = HY01D523BAdapter(
            port=self.serial_port,
            slave_id=self.slave_id,
            baudrate=self.baudrate,
            timeout=self.timeout,
        )
        return self.driver
    def set_driver(self, driver: Optional[VFDDriver]) -> None:
        self.driver = driver
        if driver is None:
            self._set_disconnected()
    def get_driver(self) -> Optional[VFDDriver]:
        return self.driver
    def get_driver_name(self) -> str:
        if self.driver is None:
            return "No Driver"
        return getattr(self.driver, "name", self.driver.__class__.__name__)
    def connect(self) -> bool:
        if self.driver is None:
            self.create_hy01d523b_driver()
        try:
            result = bool(self.driver.connect())
            if result:
                self.status.connected = True
                self.status.state = VFDState.READY
                self.status.fault = False
                self.status.fault_code = 0
                self.status.fault_text = ""
            else:
                self._set_error(getattr(self.driver, "last_error", "Connection failed."))
            return result
        except Exception as exc:
            self._set_error(str(exc))
            return False
    def disconnect(self) -> None:
        if self.driver is not None:
            try:
                self.driver.disconnect()
            except Exception:
                pass
        self._set_disconnected()
    def is_connected(self) -> bool:
        if self.driver is None:
            return False
        try:
            return bool(self.driver.is_connected())
        except Exception:
            return False
    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.target_running = False
    def set_armed(self, armed: bool) -> None:
        self.armed = bool(armed)
        if not self.armed:
            self.target_running = False
    def can_command(self) -> bool:
        return bool(self.enabled and self.armed and self.is_connected())
    def start(self) -> bool:
        if not self.can_command():
            self.status.fault_text = "VFD is not enabled, armed and connected."
            return False
        try:
            result = bool(self.driver.start())
            if result:
                self.target_running = True
                self.status.running = True
                self.status.state = VFDState.RUNNING
                self.status.direction = self.target_direction
            else:
                self._set_driver_error()
            return result
        except Exception as exc:
            self._set_error(str(exc))
            return False
    def stop(self) -> bool:
        if self.driver is None or not self.is_connected():
            self.status.fault_text = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.stop())
            if result:
                self.target_running = False
                self.status.running = False
                self.status.state = VFDState.STOPPED
            else:
                self._set_driver_error()
            return result
        except Exception as exc:
            self._set_error(str(exc))
            return False
    def emergency_stop(self) -> bool:
        return self.stop()
    def reset_fault(self) -> bool:
        if self.driver is None or not self.is_connected():
            self.status.fault_text = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.reset_fault())
            if not result:
                self._set_driver_error()
            return result
        except Exception as exc:
            self._set_error(str(exc))
            return False
    def set_frequency(self, frequency_hz: float) -> bool:
        frequency_hz = self.clamp_frequency(frequency_hz)
        self.target_frequency_hz = frequency_hz
        self.target_rpm = self.frequency_to_rpm(frequency_hz)
        if not self.can_command():
            self.status.fault_text = "VFD is not enabled, armed and connected."
            return False
        try:
            result = bool(self.driver.set_frequency(frequency_hz))
            if result:
                self.status.frequency_hz = frequency_hz
                self.status.rpm = self.target_rpm
            else:
                self._set_driver_error()
            return result
        except Exception as exc:
            self._set_error(str(exc))
            return False
    def set_speed(self, rpm: float) -> bool:
        rpm = self.clamp_rpm(rpm)
        frequency_hz = self.rpm_to_frequency(rpm)
        self.target_rpm = rpm
        self.target_frequency_hz = frequency_hz
        return self.set_frequency(frequency_hz)
    def set_direction(self, direction: VFDDirection) -> bool:
        if not isinstance(direction, VFDDirection):
            direction = VFDDirection.REVERSE if bool(direction) else VFDDirection.FORWARD
        self.target_direction = direction
        if not self.can_command():
            self.status.fault_text = "VFD is not enabled, armed and connected."
            return False
        try:
            result = bool(self.driver.set_direction(direction))
            if result:
                self.status.direction = direction
                self.status.running = True
                self.status.state = VFDState.RUNNING
            else:
                self._set_driver_error()
            return result
        except Exception as exc:
            self._set_error(str(exc))
            return False
    def frequency_to_rpm(self, frequency_hz: float) -> float:
        if self.motor.rated_frequency_hz <= 0:
            return 0.0
        return float(frequency_hz) / self.motor.rated_frequency_hz * self.motor.rated_rpm
    def rpm_to_frequency(self, rpm: float) -> float:
        if self.motor.rated_rpm <= 0:
            return 0.0
        return float(rpm) / self.motor.rated_rpm * self.motor.rated_frequency_hz
    def clamp_frequency(self, frequency_hz: float) -> float:
        low = min(self.motor.min_frequency_hz, self.motor.max_frequency_hz)
        high = max(self.motor.min_frequency_hz, self.motor.max_frequency_hz)
        return max(low, min(float(frequency_hz), high))
    def clamp_rpm(self, rpm: float) -> float:
        low = min(self.motor.min_rpm, self.motor.max_rpm)
        high = max(self.motor.min_rpm, self.motor.max_rpm)
        return max(low, min(float(rpm), high))
    def update_status(self) -> VFDStatus:
        if self.driver is None:
            self._set_disconnected()
            return self.status
        try:
            self.status = self.driver.get_status()
        except Exception as exc:
            self._set_error(str(exc))
        return self.status
    def get_status(self) -> VFDStatus:
        return self.status
    def apply_command(self, *, run: Optional[bool] = None, frequency_hz: Optional[float] = None, rpm: Optional[float] = None, reverse: Optional[bool] = None, reset: bool = False) -> bool:
        success = True
        if reset:
            if not self.reset_fault():
                success = False
        if reverse is not None:
            direction = VFDDirection.REVERSE if reverse else VFDDirection.FORWARD
            self.target_direction = direction
        if frequency_hz is not None:
            if not self.set_frequency(frequency_hz):
                success = False
        elif rpm is not None:
            if not self.set_speed(rpm):
                success = False
        if run is not None:
            if run:
                if not self.start():
                    success = False
            else:
                if not self.stop():
                    success = False
        return success
    def configure_motor(self, *, power_kw=None, voltage_v=None, rated_frequency_hz=None, rated_rpm=None, rated_current_a=None, poles=None, min_frequency_hz=None, max_frequency_hz=None, min_rpm=None, max_rpm=None) -> None:
        if power_kw is not None:
            self.motor.power_kw = float(power_kw)
        if voltage_v is not None:
            self.motor.voltage_v = float(voltage_v)
        if rated_frequency_hz is not None:
            self.motor.rated_frequency_hz = float(rated_frequency_hz)
        if rated_rpm is not None:
            self.motor.rated_rpm = float(rated_rpm)
        if rated_current_a is not None:
            self.motor.rated_current_a = float(rated_current_a)
        if poles is not None:
            self.motor.poles = int(poles)
        if min_frequency_hz is not None:
            self.motor.min_frequency_hz = float(min_frequency_hz)
        if max_frequency_hz is not None:
            self.motor.max_frequency_hz = float(max_frequency_hz)
        if min_rpm is not None:
            self.motor.min_rpm = float(min_rpm)
        if max_rpm is not None:
            self.motor.max_rpm = float(max_rpm)
    def read_parameter(self, parameter: int):
        if self.driver is None or not self.is_connected():
            self.status.fault_text = "VFD is not connected."
            return None
        try:
            return self.driver.read_parameter(int(parameter))
        except Exception as exc:
            self.status.fault_text = str(exc)
            return None
    def write_parameter(self, parameter: int, value: int) -> bool:
        if self.driver is None or not self.is_connected():
            self.status.fault_text = "VFD is not connected."
            return False
        try:
            result = bool(self.driver.write_parameter(int(parameter), int(value)))
            if not result:
                self._set_driver_error()
            return result
        except Exception as exc:
            self.status.fault_text = str(exc)
            return False
    def get_parameter(self, parameter: int):
        return self.read_parameter(parameter)
    def set_parameter(self, parameter: int, value: int) -> bool:
        return self.write_parameter(parameter, value)
    def get_last_error(self) -> str:
        if self.driver is not None:
            return str(getattr(self.driver, "last_error", self.status.fault_text))
        return self.status.fault_text
    def _set_driver_error(self) -> None:
        if self.driver is not None:
            self.status.fault_text = str(getattr(self.driver, "last_error", "VFD command failed."))
    def _set_disconnected(self) -> None:
        self.status.connected = False
        self.status.running = False
        self.status.state = VFDState.DISCONNECTED
    def _set_error(self, message: str) -> None:
        self.status.connected = False
        self.status.running = False
        self.status.state = VFDState.DISCONNECTED
        self.status.fault_text = str(message)
def create_vfd_manager(driver: Optional[VFDDriver] = None, motor_power_kw: float = 1.5, motor_voltage_v: float = 220.0, motor_frequency_hz: float = 400.0, motor_rpm: float = 24000.0) -> VFDManager:
    motor = VFDMotorConfig(
        power_kw=motor_power_kw,
        voltage_v=motor_voltage_v,
        rated_frequency_hz=motor_frequency_hz,
        rated_rpm=motor_rpm,
        max_frequency_hz=motor_frequency_hz,
        max_rpm=motor_rpm,
    )
    return VFDManager(driver=driver, motor=motor)
