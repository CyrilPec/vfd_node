from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class VFDState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    RUNNING = "running"
    FAULT = "fault"


@dataclass
class VFDStatus:
    """
    Cached state reported by the VFD.

    These values represent the last known physical state,
    not merely what we requested.
    """

    connected: bool = False
    running: bool = False
    reverse: bool = False

    frequency_hz: float = 0.0
    rpm: float = 0.0

    fault: bool = False
    fault_code: Optional[int] = None

    state: VFDState = VFDState.DISCONNECTED

    last_error: str = ""


@dataclass(frozen=True)
class VFDTarget:
    """
    Desired state requested by Blender.

    This is deliberately separate from VFDStatus.
    """

    frequency_hz: float = 0.0
    running: bool = False
    reverse: bool = False


class VFDManager:
    """
    Business/state layer between Blender and VFD communication.

    Responsibilities:
        - input validation
        - safety checks
        - desired-state management
        - command deduplication
        - error/state management

    It should NOT:
        - know about Blender nodes
        - construct serial ports
        - build Modbus frames
        - perform arbitrary serial I/O
    """

    MIN_FREQUENCY_HZ = 0.0
    MAX_FREQUENCY_HZ = 400.0

    MIN_RPM = 0.0
    MAX_RPM = 30000.0

    PARAMETER_MIN = 0
    PARAMETER_MAX = 0xFFFF

    def __init__(self, session):
        """
        session must provide the physical communication API.

        Expected session methods:

            connect()
            disconnect()
            is_connected()

            set_frequency(frequency_hz)
            start(reverse=False)
            stop()

            read_status()

            read_parameter(parameter)
            write_parameter(parameter, value)

        The manager does not care how those operations are implemented.
        """

        self.session = session

        self.enabled = True
        self.armed = False

        self.target = VFDTarget()

        self.status = VFDStatus()

        self._last_error = ""

        # Last command successfully sent to the VFD.
        #
        # This is different from self.target.
        #
        # target = what Blender wants
        # sent   = what we know we successfully sent
        self._last_sent_frequency: Optional[float] = None
        self._last_sent_running: Optional[bool] = None
        self._last_sent_reverse: Optional[bool] = None

    # ==============================================================
    # ERROR HANDLING
    # ==============================================================

    def _error(self, message: str) -> bool:
        self._last_error = str(message)

        self.status.last_error = self._last_error

        return False

    def clear_error(self) -> None:
        self._last_error = ""
        self.status.last_error = ""

    def last_error(self) -> str:
        return self._last_error

    # ==============================================================
    # CONNECTION
    # ==============================================================

    def connect(self) -> bool:
        self.clear_error()

        self.status.state = VFDState.CONNECTING

        try:
            if not self.session.connect():
                message = getattr(
                    self.session,
                    "last_error",
                    "",
                )

                return self._error(
                    message or "Failed to connect to VFD."
                )

        except Exception as exc:
            return self._error(
                f"VFD connection failed: {exc}"
            )

        self.status.connected = True
        self.status.state = VFDState.READY

        return True

    def disconnect(self) -> None:
        try:
            self.session.disconnect()
        except Exception as exc:
            self._last_error = str(exc)

        self.status.connected = False
        self.status.running = False
        self.status.state = VFDState.DISCONNECTED

        self._last_sent_frequency = None
        self._last_sent_running = None
        self._last_sent_reverse = None

    def is_connected(self) -> bool:
        try:
            connected = bool(
                self.session.is_connected()
            )
        except Exception as exc:
            self._error(str(exc))
            connected = False

        self.status.connected = connected

        if not connected:
            self.status.running = False

            if self.status.state != VFDState.FAULT:
                self.status.state = VFDState.DISCONNECTED

        return connected

    # ==============================================================
    # ENABLE / ARM
    # ==============================================================

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)

        self.enabled = enabled

        if not enabled:
            # Disabling the controller must never leave the VFD
            # running.
            self.target = VFDTarget(
                frequency_hz=self.target.frequency_hz,
                running=False,
                reverse=self.target.reverse,
            )

            self.stop()

    def set_armed(self, armed: bool) -> None:
        armed = bool(armed)

        self.armed = armed

        if not armed:
            # Disarming also forces a stop request.
            self.target = VFDTarget(
                frequency_hz=self.target.frequency_hz,
                running=False,
                reverse=self.target.reverse,
            )

            self.stop()

    # ==============================================================
    # VALIDATION
    # ==============================================================

    def _validate_frequency(
        self,
        frequency_hz: float,
    ) -> Optional[float]:
        try:
            value = float(frequency_hz)
        except (TypeError, ValueError):
            self._error(
                "Frequency must be a number."
            )
            return None

        if not value == value:
            self._error(
                "Frequency cannot be NaN."
            )
            return None

        if value < self.MIN_FREQUENCY_HZ:
            self._error(
                f"Frequency cannot be below "
                f"{self.MIN_FREQUENCY_HZ} Hz."
            )
            return None

        if value > self.MAX_FREQUENCY_HZ:
            self._error(
                f"Frequency cannot exceed "
                f"{self.MAX_FREQUENCY_HZ} Hz."
            )
            return None

        return value

    def _validate_rpm(
        self,
        rpm: float,
    ) -> Optional[float]:
        try:
            value = float(rpm)
        except (TypeError, ValueError):
            self._error(
                "RPM must be a number."
            )
            return None

        if not value == value:
            self._error(
                "RPM cannot be NaN."
            )
            return None

        if value < self.MIN_RPM:
            self._error(
                f"RPM cannot be below {self.MIN_RPM}."
            )
            return None

        if value > self.MAX_RPM:
            self._error(
                f"RPM cannot exceed {self.MAX_RPM}."
            )
            return None

        return value

    def _validate_parameter(
        self,
        parameter: int,
        value: int,
    ) -> Optional[tuple[int, int]]:
        try:
            parameter = int(parameter)
        except (TypeError, ValueError):
            self._error(
                "Parameter number must be an integer."
            )
            return None

        try:
            value = int(value)
        except (TypeError, ValueError):
            self._error(
                "Parameter value must be an integer."
            )
            return None

        if not (
            self.PARAMETER_MIN
            <= value
            <= self.PARAMETER_MAX
        ):
            self._error(
                "Parameter value must be between "
                f"{self.PARAMETER_MIN} and "
                f"{self.PARAMETER_MAX}."
            )
            return None

        return parameter, value

    # ==============================================================
    # TARGET STATE
    # ==============================================================

    def set_target(
        self,
        frequency_hz: float,
        running: bool,
        reverse: bool,
    ) -> bool:
        """
        Set desired VFD state.

        IMPORTANT:
        This method does not blindly send all values.

        Unchanged values are ignored.
        """

        frequency = self._validate_frequency(
            frequency_hz
        )

        if frequency is None:
            return False

        running = bool(running)
        reverse = bool(reverse)

        # Safety rules.
        if not self.enabled:
            running = False

        if not self.armed:
            running = False

        self.target = VFDTarget(
            frequency_hz=frequency,
            running=running,
            reverse=reverse,
        )

        return self.apply_target()

    # ==============================================================
    # COMMAND APPLICATION
    # ==============================================================

    def apply_target(self) -> bool:
        """
        Apply only changes that are actually required.

        This is the key command-deduplication layer.
        """

        if not self.is_connected():
            return self._error(
                "Cannot control VFD: not connected."
            )

        target = self.target

        # ----------------------------------------------------------
        # Frequency
        # ----------------------------------------------------------

        if (
            self._last_sent_frequency is None
            or target.frequency_hz
            != self._last_sent_frequency
        ):
            try:
                result = self.session.set_frequency(
                    target.frequency_hz
                )
            except Exception as exc:
                return self._error(
                    f"Frequency command failed: {exc}"
                )

            if not result:
                return self._error(
                    self._session_error(
                        "Frequency command failed."
                    )
                )

            self._last_sent_frequency = (
                target.frequency_hz
            )

        # ----------------------------------------------------------
        # Run / stop
        # ----------------------------------------------------------

        if target.running:
            if (
                self._last_sent_running is not True
                or self._last_sent_reverse
                != target.reverse
            ):
                try:
                    result = self.session.start(
                        reverse=target.reverse
                    )
                except Exception as exc:
                    return self._error(
                        f"Start command failed: {exc}"
                    )

                if not result:
                    return self._error(
                        self._session_error(
                            "Start command failed."
                        )
                    )

                self._last_sent_running = True
                self._last_sent_reverse = (
                    target.reverse
                )

        else:
            if self._last_sent_running is not False:
                try:
                    result = self.session.stop()
                except Exception as exc:
                    return self._error(
                        f"Stop command failed: {exc}"
                    )

                if not result:
                    return self._error(
                        self._session_error(
                            "Stop command failed."
                        )
                    )

                self._last_sent_running = False
                self._last_sent_reverse = False

        self.clear_error()

        return True

    def apply_command(
        self,
        run: bool,
        reverse: bool,
        frequency_hz: float,
    ) -> bool:
        """
        Compatibility wrapper for existing callers.
        """

        return self.set_target(
            frequency_hz=frequency_hz,
            running=run,
            reverse=reverse,
        )

    # ==============================================================
    # STOP / EMERGENCY STOP
    # ==============================================================

    def stop(self) -> bool:
        """
        Normal stop.

        Does not disconnect the VFD.
        """

        if not self.is_connected():
            return self._error(
                "Cannot stop VFD: not connected."
            )

        self.target = VFDTarget(
            frequency_hz=self.target.frequency_hz,
            running=False,
            reverse=self.target.reverse,
        )

        try:
            result = self.session.stop()
        except Exception as exc:
            return self._error(
                f"Stop command failed: {exc}"
            )

        if not result:
            return self._error(
                self._session_error(
                    "Stop command failed."
                )
            )

        self._last_sent_running = False
        self._last_sent_reverse = False

        self.status.running = False

        if self.status.connected:
            self.status.state = VFDState.READY

        self.clear_error()

        return True

    def emergency_stop(self) -> bool:
        """
        Software emergency stop.

        This is NOT a safety-rated emergency stop.
        Physical safety circuitry/STO is required for
        actual machine safety.
        """

        self.target = VFDTarget(
            frequency_hz=self.target.frequency_hz,
            running=False,
            reverse=self.target.reverse,
        )

        return self.stop()

    # ==============================================================
    # STATUS
    # ==============================================================

    def update_status(self) -> VFDStatus:
        """
        Synchronous status refresh.

        The communication/session layer should eventually perform
        this operation in its worker and update the cached status.

        Blender should preferably call get_status(), not this method.
        """

        if not self.is_connected():
            self.status.connected = False
            self.status.state = (
                VFDState.DISCONNECTED
            )
            return self.status

        try:
            new_status = self.session.read_status()

        except Exception as exc:
            self._error(
                f"Status read failed: {exc}"
            )

            self.status.state = VFDState.FAULT

            return self.status

        if new_status is None:
            return self.status

        self._merge_status(new_status)

        return self.status

    def get_status(self) -> VFDStatus:
        """
        Return cached status.

        IMPORTANT:
        This method must never perform hardware I/O.
        """

        return self.status

    def _merge_status(self, new_status) -> None:
        """
        Convert driver/session status into our stable status object.

        Supports both VFDStatus and simple objects/dicts.
        """

        if isinstance(new_status, VFDStatus):
            self.status = new_status
            return

        if isinstance(new_status, dict):
            for key, value in new_status.items():
                if hasattr(self.status, key):
                    setattr(
                        self.status,
                        key,
                        value,
                    )
        else:
            for key in (
                "connected",
                "running",
                "reverse",
                "frequency_hz",
                "rpm",
                "fault",
                "fault_code",
            ):
                if hasattr(new_status, key):
                    setattr(
                        self.status,
                        key,
                        getattr(new_status, key),
                    )

        if self.status.fault:
            self.status.state = VFDState.FAULT
        elif self.status.running:
            self.status.state = VFDState.RUNNING
        elif self.status.connected:
            self.status.state = VFDState.READY
        else:
            self.status.state = (
                VFDState.DISCONNECTED
            )

    # ==============================================================
    # PARAMETERS
    # ==============================================================

    def read_parameter(
        self,
        parameter: int,
    ):
        if not self.is_connected():
            self._error(
                "Cannot read parameter: "
                "VFD is not connected."
            )
            return None

        try:
            result = self.session.read_parameter(
                parameter
            )
        except Exception as exc:
            self._error(
                f"Parameter read failed: {exc}"
            )
            return None

        return result

    def write_parameter(
        self,
        parameter: int,
        value: int,
    ) -> bool:
        validated = self._validate_parameter(
            parameter,
            value,
        )

        if validated is None:
            return False

        parameter, value = validated

        if not self.is_connected():
            return self._error(
                "Cannot write parameter: "
                "VFD is not connected."
            )

        try:
            result = self.session.write_parameter(
                parameter,
                value,
            )
        except Exception as exc:
            return self._error(
                f"Parameter write failed: {exc}"
            )

        if not result:
            return self._error(
                self._session_error(
                    "Parameter write failed."
                )
            )

        self.clear_error()

        return True

    # ==============================================================
    # HELPERS
    # ==============================================================

    def _session_error(
        self,
        fallback: str,
    ) -> str:
        message = getattr(
            self.session,
            "last_error",
            "",
        )

        if callable(message):
            try:
                message = message()
            except Exception:
                message = ""

        return str(message or fallback)
