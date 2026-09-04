"""
vfd_manager.py

Universal VFD manager for Scn6Studio.

This module intentionally contains NO Modbus implementation.

Architecture:

    SCN6 VFD Node
          |
          v
      VFDManager
          |
          v
    VFD Driver API
          |
          +-- Modbus RTU
          +-- Modbus TCP
          +-- Other drivers

The manager exposes logical VFD operations such as:

    start()
    stop()
    set_frequency()
    set_speed()
    set_direction()
    reset_fault()
    emergency_stop()
    get_status()

Drivers are responsible for translating these operations into
the protocol/registers required by a particular VFD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# =============================================================================
# ENUMS
# =============================================================================


class VFDState(Enum):
    """
    Generic VFD operating state.
    """

    UNKNOWN = "unknown"
    DISCONNECTED = "disconnected"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FAULT = "fault"
    EMERGENCY_STOP = "emergency_stop"


class VFDDirection(Enum):
    """
    Generic spindle direction.
    """

    FORWARD = "forward"
    REVERSE = "reverse"


# =============================================================================
# STATUS
# =============================================================================


@dataclass
class VFDStatus:
    """
    Universal VFD status.

    A driver converts its native status information into this structure.
    """

    connected: bool = False

    state: VFDState = VFDState.UNKNOWN

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


# =============================================================================
# MOTOR CONFIGURATION
# =============================================================================


@dataclass
class VFDMotorConfig:
    """
    Motor configuration.

    These values describe the spindle/motor, not the communication protocol.
    """

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


# =============================================================================
# DRIVER BASE CLASS
# =============================================================================


class VFDDriver:
    """
    Base interface for VFD communication drivers.

    A real driver should inherit from this class.

    Example:

        class ModbusVFDDriver(VFDDriver):
            ...
    """

    name = "Generic VFD Driver"

    # -------------------------------------------------------------------------
    # CONNECTION
    # -------------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Connect to the VFD.

        Returns:
            True if connection succeeded.
        """

        raise NotImplementedError

    def disconnect(self) -> None:
        """
        Disconnect from the VFD.
        """

        raise NotImplementedError

    def is_connected(self) -> bool:
        """
        Return connection state.
        """

        return False

    # -------------------------------------------------------------------------
    # COMMANDS
    # -------------------------------------------------------------------------

    def start(self) -> bool:
        """
        Start the VFD.
        """

        raise NotImplementedError

    def stop(self) -> bool:
        """
        Stop the VFD.
        """

        raise NotImplementedError

    def emergency_stop(self) -> bool:
        """
        Emergency stop command.

        The actual implementation depends on the VFD.
        """

        raise NotImplementedError

    def reset_fault(self) -> bool:
        """
        Reset VFD fault.
        """

        raise NotImplementedError

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        """
        Set target frequency.
        """

        raise NotImplementedError

    def set_speed(
        self,
        rpm: float,
    ) -> bool:
        """
        Set target speed.
        """

        raise NotImplementedError

    def set_direction(
        self,
        direction: VFDDirection,
    ) -> bool:
        """
        Set spindle direction.
        """

        raise NotImplementedError

    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------

    def get_status(self) -> VFDStatus:
        """
        Read and return normalized VFD status.
        """

        raise NotImplementedError


# =============================================================================
# VFD MANAGER
# =============================================================================


class VFDManager:
    """
    Universal VFD manager.

    The manager provides a stable interface to the Blender node.

    It does not know anything about:

        - Modbus registers
        - Modbus function codes
        - Serial ports
        - TCP sockets
        - specific VFD brands

    Those things belong inside a driver.
    """

    def __init__(
        self,
        driver: Optional[VFDDriver] = None,
        motor: Optional[VFDMotorConfig] = None,
    ):

        self.driver = driver

        self.motor = motor or VFDMotorConfig()

        self.status = VFDStatus()

        self.enabled = True

        self.armed = False

        self.target_frequency_hz = 0.0

        self.target_rpm = 0.0

        self.target_running = False

        self.target_direction = VFDDirection.FORWARD

    # =========================================================================
    # DRIVER
    # =========================================================================

    def set_driver(
        self,
        driver: Optional[VFDDriver],
    ) -> None:
        """
        Assign or replace the communication driver.
        """

        self.driver = driver

        if driver is None:

            self.status = VFDStatus(
                connected=False,
                state=VFDState.DISCONNECTED,
            )

    def get_driver_name(self) -> str:
        """
        Return current driver name.
        """

        if self.driver is None:
            return "No Driver"

        return getattr(
            self.driver,
            "name",
            self.driver.__class__.__name__,
        )

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def connect(self) -> bool:
        """
        Connect the configured driver.
        """

        if self.driver is None:
            self._set_disconnected()
            return False

        try:

            result = bool(
                self.driver.connect()
            )

            if result:

                self.status.connected = True

                if self.status.state == VFDState.UNKNOWN:

                    self.status.state = VFDState.READY

            else:

                self._set_disconnected()

            return result

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    def disconnect(self) -> None:
        """
        Disconnect the driver.
        """

        if self.driver is not None:

            try:
                self.driver.disconnect()

            except Exception:
                pass

        self._set_disconnected()

    def is_connected(self) -> bool:
        """
        Return whether the VFD is connected.
        """

        if self.driver is None:
            return False

        try:

            return bool(
                self.driver.is_connected()
            )

        except Exception:

            return self.status.connected

    # =========================================================================
    # SAFETY
    # =========================================================================

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        """
        Enable or disable VFD commands.
        """

        self.enabled = bool(enabled)

        if not self.enabled:

            self.target_running = False

    def set_armed(
        self,
        armed: bool,
    ) -> None:
        """
        ARM / disarm the VFD command interface.
        """

        self.armed = bool(armed)

        if not self.armed:

            self.target_running = False

    def can_command(self) -> bool:
        """
        Check whether normal commands are allowed.
        """

        return (
            self.enabled
            and self.armed
            and self.driver is not None
            and self.is_connected()
        )

    # =========================================================================
    # START / STOP
    # =========================================================================

    def start(self) -> bool:
        """
        Start spindle.
        """

        if not self.can_command():
            return False

        try:

            result = bool(
                self.driver.start()
            )

            if result:
                self.target_running = True

            return result

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    def stop(self) -> bool:
        """
        Stop spindle.
        """

        if self.driver is None:
            return False

        if not self.is_connected():
            return False

        try:

            result = bool(
                self.driver.stop()
            )

            if result:
                self.target_running = False

            return result

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    def emergency_stop(self) -> bool:
        """
        Emergency stop.

        Unlike normal stop, this is allowed even when the manager
        is not armed, provided a driver is connected.
        """

        if self.driver is None:
            return False

        if not self.is_connected():
            return False

        try:

            result = bool(
                self.driver.emergency_stop()
            )

            if result:

                self.target_running = False

                self.status.state = (
                    VFDState.EMERGENCY_STOP
                )

            return result

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    # =========================================================================
    # RESET
    # =========================================================================

    def reset_fault(self) -> bool:
        """
        Reset VFD fault.
        """

        if self.driver is None:
            return False

        if not self.is_connected():
            return False

        try:

            return bool(
                self.driver.reset_fault()
            )

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    # =========================================================================
    # FREQUENCY
    # =========================================================================

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        """
        Set target frequency.

        The value is clamped to the configured motor limits.
        """

        frequency_hz = self.clamp_frequency(
            frequency_hz
        )

        self.target_frequency_hz = frequency_hz

        self.target_rpm = (
            self.frequency_to_rpm(
                frequency_hz
            )
        )

        if not self.can_command():
            return False

        try:

            return bool(
                self.driver.set_frequency(
                    frequency_hz
                )
            )

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    # =========================================================================
    # RPM
    # =========================================================================

    def set_speed(
        self,
        rpm: float,
    ) -> bool:
        """
        Set target spindle RPM.

        RPM is converted into frequency using the motor configuration.
        """

        rpm = self.clamp_rpm(
            rpm
        )

        frequency_hz = (
            self.rpm_to_frequency(
                rpm
            )
        )

        self.target_rpm = rpm

        self.target_frequency_hz = (
            frequency_hz
        )

        if not self.can_command():
            return False

        try:

            return bool(
                self.driver.set_speed(
                    rpm
                )
            )

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    # =========================================================================
    # DIRECTION
    # =========================================================================

    def set_direction(
        self,
        direction: VFDDirection,
    ) -> bool:
        """
        Set spindle direction.
        """

        if not isinstance(
            direction,
            VFDDirection,
        ):

            direction = (
                VFDDirection.REVERSE
                if bool(direction)
                else VFDDirection.FORWARD
            )

        self.target_direction = direction

        if not self.can_command():
            return False

        try:

            return bool(
                self.driver.set_direction(
                    direction
                )
            )

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return False

    # =========================================================================
    # MOTOR CONVERSION
    # =========================================================================

    def frequency_to_rpm(
        self,
        frequency_hz: float,
    ) -> float:
        """
        Convert frequency to RPM.

        Uses configured rated frequency and rated RPM.

        Example:

            400 Hz -> 24000 RPM
            200 Hz -> 12000 RPM
        """

        rated_frequency = (
            self.motor.rated_frequency_hz
        )

        rated_rpm = (
            self.motor.rated_rpm
        )

        if rated_frequency <= 0.0:
            return 0.0

        return (
            float(frequency_hz)
            / rated_frequency
            * rated_rpm
        )

    def rpm_to_frequency(
        self,
        rpm: float,
    ) -> float:
        """
        Convert RPM to frequency.
        """

        rated_rpm = (
            self.motor.rated_rpm
        )

        rated_frequency = (
            self.motor.rated_frequency_hz
        )

        if rated_rpm <= 0.0:
            return 0.0

        return (
            float(rpm)
            / rated_rpm
            * rated_frequency
        )

    # =========================================================================
    # LIMITS
    # =========================================================================

    def clamp_frequency(
        self,
        frequency_hz: float,
    ) -> float:
        """
        Clamp frequency to configured limits.
        """

        low = min(
            self.motor.min_frequency_hz,
            self.motor.max_frequency_hz,
        )

        high = max(
            self.motor.min_frequency_hz,
            self.motor.max_frequency_hz,
        )

        return max(
            low,
            min(
                float(frequency_hz),
                high,
            ),
        )

    def clamp_rpm(
        self,
        rpm: float,
    ) -> float:
        """
        Clamp RPM to configured limits.
        """

        low = min(
            self.motor.min_rpm,
            self.motor.max_rpm,
        )

        high = max(
            self.motor.min_rpm,
            self.motor.max_rpm,
        )

        return max(
            low,
            min(
                float(rpm),
                high,
            ),
        )

    # =========================================================================
    # STATUS
    # =========================================================================

    def update_status(self) -> VFDStatus:
        """
        Read current status from the driver.

        The driver is responsible for translating native VFD data
        into VFDStatus.
        """

        if self.driver is None:

            self._set_disconnected()

            return self.status

        try:

            status = self.driver.get_status()

            if status is not None:

                self.status = status

            return self.status

        except Exception as exc:

            self._set_error(
                str(exc)
            )

            return self.status

    def get_status(self) -> VFDStatus:
        """
        Return cached status.

        Use update_status() when fresh hardware data is required.
        """

        return self.status

    # =========================================================================
    # HIGH LEVEL COMMAND
    # =========================================================================

    def apply_command(
        self,
        *,
        run: Optional[bool] = None,
        frequency_hz: Optional[float] = None,
        rpm: Optional[float] = None,
        reverse: Optional[bool] = None,
        reset: bool = False,
    ) -> bool:
        """
        Apply a complete logical VFD command.

        This is the method the Blender node can use each update cycle.

        Example:

            manager.apply_command(
                run=True,
                frequency_hz=250,
                reverse=False,
            )
        """

        success = True

        # ---------------------------------------------------------------------
        # RESET
        # ---------------------------------------------------------------------

        if reset:

            if not self.reset_fault():
                success = False

        # ---------------------------------------------------------------------
        # DIRECTION
        # ---------------------------------------------------------------------

        if reverse is not None:

            direction = (
                VFDDirection.REVERSE
                if reverse
                else VFDDirection.FORWARD
            )

            if not self.set_direction(
                direction
            ):

                success = False

        # ---------------------------------------------------------------------
        # FREQUENCY
        # ---------------------------------------------------------------------

        if frequency_hz is not None:

            if not self.set_frequency(
                frequency_hz
            ):

                success = False

        # ---------------------------------------------------------------------
        # RPM
        # ---------------------------------------------------------------------

        elif rpm is not None:

            if not self.set_speed(
                rpm
            ):

                success = False

        # ---------------------------------------------------------------------
        # RUN
        # ---------------------------------------------------------------------

        if run is not None:

            if run:

                if not self.start():
                    success = False

            else:

                if not self.stop():
                    success = False

        return success

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def configure_motor(
        self,
        *,
        power_kw: Optional[float] = None,
        voltage_v: Optional[float] = None,
        rated_frequency_hz: Optional[float] = None,
        rated_rpm: Optional[float] = None,
        rated_current_a: Optional[float] = None,
        poles: Optional[int] = None,
        min_frequency_hz: Optional[float] = None,
        max_frequency_hz: Optional[float] = None,
        min_rpm: Optional[float] = None,
        max_rpm: Optional[float] = None,
    ) -> None:
        """
        Update motor configuration.
        """

        if power_kw is not None:
            self.motor.power_kw = float(power_kw)

        if voltage_v is not None:
            self.motor.voltage_v = float(voltage_v)

        if rated_frequency_hz is not None:
            self.motor.rated_frequency_hz = float(
                rated_frequency_hz
            )

        if rated_rpm is not None:
            self.motor.rated_rpm = float(
                rated_rpm
            )

        if rated_current_a is not None:
            self.motor.rated_current_a = float(
                rated_current_a
            )

        if poles is not None:
            self.motor.poles = int(poles)

        if min_frequency_hz is not None:
            self.motor.min_frequency_hz = float(
                min_frequency_hz
            )

        if max_frequency_hz is not None:
            self.motor.max_frequency_hz = float(
                max_frequency_hz
            )

        if min_rpm is not None:
            self.motor.min_rpm = float(
                min_rpm
            )

        if max_rpm is not None:
            self.motor.max_rpm = float(
                max_rpm
            )

    # =========================================================================
    # INTERNAL STATE HELPERS
    # =========================================================================

    def _set_disconnected(self) -> None:
        """
        Set manager state to disconnected.
        """

        self.status.connected = False

        self.status.running = False

        self.status.state = (
            VFDState.DISCONNECTED
        )

    def _set_error(
        self,
        message: str,
    ) -> None:
        """
        Store a generic communication error.

        The manager does not assign a VFD fault code here because
        communication errors and VFD faults are different things.
        """

        self.status.connected = False

        self.status.state = (
            VFDState.DISCONNECTED
        )

        self.status.fault_text = str(
            message
        )


# =============================================================================
# NULL / SIMULATION DRIVER
# =============================================================================


class NullVFDDriver(VFDDriver):
    """
    Dummy driver for testing the node without hardware.

    This is useful while developing the Blender node.

    It does not communicate with anything.
    """

    name = "Simulation VFD"

    def __init__(self):

        self.connected = False

        self.running = False

        self.direction = (
            VFDDirection.FORWARD
        )

        self.frequency_hz = 0.0

        self.fault = False

        self.fault_code = 0

    # -------------------------------------------------------------------------
    # CONNECTION
    # -------------------------------------------------------------------------

    def connect(self) -> bool:

        self.connected = True

        return True

    def disconnect(self) -> None:

        self.connected = False

        self.running = False

    def is_connected(self) -> bool:

        return self.connected

    # -------------------------------------------------------------------------
    # COMMANDS
    # -------------------------------------------------------------------------

    def start(self) -> bool:

        if not self.connected:
            return False

        self.running = True

        return True

    def stop(self) -> bool:

        if not self.connected:
            return False

        self.running = False

        return True

    def emergency_stop(self) -> bool:

        if not self.connected:
            return False

        self.running = False

        return True

    def reset_fault(self) -> bool:

        self.fault = False

        self.fault_code = 0

        return True

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:

        if not self.connected:
            return False

        self.frequency_hz = float(
            frequency_hz
        )

        return True

    def set_speed(
        self,
        rpm: float,
    ) -> bool:

        if not self.connected:
            return False

        # Simulation driver doesn't need RPM directly.
        # The manager normally converts RPM -> Hz.
        return True

    def set_direction(
        self,
        direction: VFDDirection,
    ) -> bool:

        if not self.connected:
            return False

        self.direction = direction

        return True

    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------

    def get_status(self) -> VFDStatus:

        if not self.connected:

            return VFDStatus(
                connected=False,
                state=VFDState.DISCONNECTED,
            )

        state = (
            VFDState.RUNNING
            if self.running
            else VFDState.STOPPED
        )

        return VFDStatus(

            connected=True,

            state=state,

            running=self.running,

            direction=self.direction,

            frequency_hz=self.frequency_hz,

            fault=self.fault,

            fault_code=self.fault_code,
        )


# =============================================================================
# FACTORY
# =============================================================================


def create_vfd_manager(
    driver: Optional[VFDDriver] = None,
    motor_power_kw: float = 1.5,
    motor_voltage_v: float = 220.0,
    motor_frequency_hz: float = 400.0,
    motor_rpm: float = 24000.0,
) -> VFDManager:
    """
    Convenience factory.

    Example:

        manager = create_vfd_manager()

        manager.set_driver(
            NullVFDDriver()
        )
    """

    motor = VFDMotorConfig(

        power_kw=motor_power_kw,

        voltage_v=motor_voltage_v,

        rated_frequency_hz=motor_frequency_hz,

        rated_rpm=motor_rpm,

        max_frequency_hz=motor_frequency_hz,

        max_rpm=motor_rpm,
    )

    return VFDManager(
        driver=driver,
        motor=motor,
    )


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":

    manager = create_vfd_manager(
        driver=NullVFDDriver()
    )

    print(
        "Driver:",
        manager.get_driver_name()
    )

    print(
        "Connect:",
        manager.connect()
    )

    manager.set_armed(True)

    print(
        "Set 200 Hz:",
        manager.set_frequency(200.0)
    )

    print(
        "Start:",
        manager.start()
    )

    status = manager.update_status()

    print(
        "Connected:",
        status.connected
    )

    print(
        "Running:",
        status.running
    )

    print(
        "Frequency:",
        status.frequency_hz,
        "Hz"
    )

    print(
        "RPM:",
        manager.frequency_to_rpm(
            status.frequency_hz
        )
    )

    print(
        "Stop:",
        manager.stop()
    )
