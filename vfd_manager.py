from __future__ import annotations

import math
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
    Normalized status exposed to the API / Blender.

    These values are the latest known physical/cached state.
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
    Desired state.

    This is NOT the same thing as physical VFD state.
    """

    frequency_hz: float = 0.0
    running: bool = False
    reverse: bool = False


class VFDManager:
    """
    Business/state layer between Blender/API and VFDSession.

    Responsibilities:
        - validation
        - safety rules
        - desired state
        - command deduplication
        - status normalization
        - error handling

    VFDManager NEVER performs hardware I/O directly.

    Session methods such as set_frequency(), start() and stop()
    only queue commands. The worker performs the actual I/O.
    """

    MIN_FREQUENCY_HZ = 0.0
    MAX_FREQUENCY_HZ = 400.0

    MIN_RPM = 0.0
    MAX_RPM = 30000.0

    PARAMETER_MIN = 0
    PARAMETER_MAX = 0xFFFF

    def __init__(self, session):
        self.session = session

        self.enabled = True
        self.armed = False

        self.target = VFDTarget()
        self.status = VFDStatus()

        self._last_error = ""

        # --------------------------------------------------------------
        # Queued/desired command state.
        #
        # These are NOT "confirmed by hardware".
        #
        # They mean:
        #   the manager has already submitted this state to the session.
        # --------------------------------------------------------------

        self._queued_frequency: Optional[float] = None
        self._queued_running: Optional[bool] = None
        self._queued_reverse: Optional[bool] = None

    # ==================================================================
    # ERROR HANDLING
    # ==================================================================

    def _error(self, message: str) -> bool:
        message = str(message)

        self._last_error = message
        self.status.last_error = message

        return False

    def clear_error(self) -> None:
        self._last_error = ""
        self.status.last_error = ""

    def last_error(self) -> str:
        """
        Always prefer the session's latest communication error.
        """

        session_error = getattr(
            self.session,
            "last_error",
            "",
        )

        if callable(session_error):
            try:
                session_error = session_error()
            except Exception:
                session_error = ""

        if session_error:
            return str(session_error)

        return self._last_error

    def _set_error_from_session(
        self,
        fallback: str,
    ) -> bool:
        message = self.last_error()

        return self._error(
            message or fallback
        )

    # ==================================================================
    # CONNECTION
    # ==================================================================

    def connect(self) -> bool:
        self.clear_error()

        self.status.state = VFDState.CONNECTING

        try:
            result = self.session.connect()

        except Exception as exc:
            self.status.connected = False
            self.status.state = VFDState.DISCONNECTED

            return self._error(
                f"VFD connection failed: {exc}"
            )

        if not result:
            self.status.connected = False
            self.status.state = VFDState.DISCONNECTED

            return self._set_error_from_session(
                "Failed to connect to VFD."
            )

        self.status.connected = True
        self.status.state = VFDState.READY

        # The worker owns status polling.
        self._sync_cached_status()

        return True

    def disconnect(self) -> None:
        try:
            self.session.disconnect()

        except Exception as exc:
            self._last_error = str(exc)

        self.status = VFDStatus()

        self._queued_frequency = None
        self._queued_running = None
        self._queued_reverse = None

    def is_connected(self) -> bool:
        """
        This must remain cheap.

        It checks the session state; it does not perform a VFD read.
        """

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
                self.status.state = (
                    VFDState.DISCONNECTED
                )

        return connected

    # ==================================================================
    # ENABLE / ARM
    # ==================================================================

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        enabled = bool(enabled)

        if self.enabled == enabled:
            return

        self.enabled = enabled

        if not enabled:
            self._force_target_stop()

    def set_armed(
        self,
        armed: bool,
    ) -> None:
        armed = bool(armed)

        if self.armed == armed:
            return

        self.armed = armed

        if not armed:
            self._force_target_stop()

    def _force_target_stop(self) -> None:
        self.target = VFDTarget(
            frequency_hz=self.target.frequency_hz,
            running=False,
            reverse=self.target.reverse,
        )

        # STOP is explicitly submitted.
        self._queued_running = False

        try:
            result = self.session.stop()

        except Exception as exc:
            self._error(
                f"Stop command failed: {exc}"
            )
            return

        if not result:
            self._set_error_from_session(
                "Stop command could not be queued."
            )
            return

        self._queued_running = False
        self._queued_reverse = False

    # ==================================================================
    # VALIDATION
    # ==================================================================

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

        if not math.isfinite(value):
            self._error(
                "Frequency must be finite."
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

        if not math.isfinite(value):
            self._error(
                "RPM must be finite."
            )
            return None

        if value < self.MIN_RPM:
            self._error(
                f"RPM cannot be below "
                f"{self.MIN_RPM}."
            )
            return None

        if value > self.MAX_RPM:
            self._error(
                f"RPM cannot exceed "
                f"{self.MAX_RPM}."
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

    # ==================================================================
    # TARGET
    # ==================================================================

    def set_target(
        self,
        frequency_hz: float,
        running: bool,
        reverse: bool,
    ) -> bool:

        frequency = self._validate_frequency(
            frequency_hz
        )

        if frequency is None:
            return False

        running = bool(running)
        reverse = bool(reverse)

        # --------------------------------------------------------------
        # Safety
        # --------------------------------------------------------------

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

    # ==================================================================
    # COMMAND QUEUING
    # ==================================================================

    def apply_target(self) -> bool:
        """
        Submit only changed desired commands.

        IMPORTANT:

        session.set_frequency() / start() / stop() now mean:

            "command accepted by the session"

        NOT:

            "command has already reached the VFD"

        The worker is responsible for physical execution.
        """

        if not self.is_connected():
            return self._error(
                "Cannot control VFD: not connected."
            )

        target = self.target

        # --------------------------------------------------------------
        # Frequency
        # --------------------------------------------------------------

        if (
            self._queued_frequency is None
            or not math.isclose(
                target.frequency_hz,
                self._queued_frequency,
                rel_tol=0.0,
                abs_tol=0.001,
            )
        ):
            try:
                result = (
                    self.session.set_frequency(
                        target.frequency_hz
                    )
                )

            except Exception as exc:
                return self._error(
                    f"Frequency command failed: {exc}"
                )

            if not result:
                return self._set_error_from_session(
                    "Frequency command could not be queued."
                )

            self._queued_frequency = (
                target.frequency_hz
            )

        # --------------------------------------------------------------
        # Run / stop / direction
        # --------------------------------------------------------------

        if target.running:

            direction_changed = (
                self._queued_reverse
                != target.reverse
            )

            run_changed = (
                self._queued_running is not True
            )

            if run_changed or direction_changed:

                try:
                    result = self.session.start(
                        reverse=target.reverse
                    )

                except Exception as exc:
                    return self._error(
                        f"Start command failed: {exc}"
                    )

                if not result:
                    return self._set_error_from_session(
                        "Start command could not be queued."
                    )

                self._queued_running = True
                self._queued_reverse = (
                    target.reverse
                )

        else:

            if self._queued_running is not False:

                try:
                    result = self.session.stop()

                except Exception as exc:
                    return self._error(
                        f"Stop command failed: {exc}"
                    )

                if not result:
                    return self._set_error_from_session(
                        "Stop command could not be queued."
                    )

                self._queued_running = False
                self._queued_reverse = False

        self.clear_error()

        return True

    def apply_command(
        self,
        run: bool,
        reverse: bool,
        frequency_hz: float,
    ) -> bool:
        """
        Compatibility method used by VFDAPI.
        """

        return self.set_target(
            frequency_hz=frequency_hz,
            running=run,
            reverse=reverse,
        )

    # ==================================================================
    # STOP
    # ==================================================================

    def stop(self) -> bool:

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
            return self._set_error_from_session(
                "Stop command could not be queued."
            )

        self._queued_running = False
        self._queued_reverse = False

        # This is desired/cached local state only.
        # The worker will confirm actual hardware state.
        self.status.running = False

        if self.status.connected:
            self.status.state = VFDState.READY

        self.clear_error()

        return True

    def emergency_stop(self) -> bool:
        """
        Software emergency stop.

        This is NOT a safety-rated emergency stop.
        Use physical STO/safety circuitry for machine safety.
        """

        self.target = VFDTarget(
            frequency_hz=self.target.frequency_hz,
            running=False,
            reverse=self.target.reverse,
        )

        try:
            result = self.session.stop()

        except Exception as exc:
            return self._error(
                f"Emergency stop failed: {exc}"
            )

        if not result:
            return self._set_error_from_session(
                "Emergency stop could not be queued."
            )

        self._queued_running = False
        self._queued_reverse = False

        self.status.running = False

        self.clear_error()

        return True

    # ==================================================================
    # STATUS
    # ==================================================================

    def update_status(self) -> VFDStatus:
        """
        Compatibility method.

        IMPORTANT:
        This no longer performs hardware I/O.

        Status is already polled by VFDSession's worker.
        """

        self._sync_cached_status()

        return self.status

    def get_status(self) -> VFDStatus:
        """
        Return cached/normalized status.

        NEVER performs hardware I/O.
        """

        self._sync_cached_status()

        return self.status

    def _sync_cached_status(self) -> None:
        """
        Convert VFDSession's driver-specific status dictionary
        into our stable VFDStatus object.
        """

        try:
            raw = self.session.get_status()

        except Exception as exc:
            self._error(
                f"Could not read cached VFD status: {exc}"
            )
            return

        if not raw:
            return

        # --------------------------------------------------------------
        # Connection
        # --------------------------------------------------------------

        if "connected" in raw:
            self.status.connected = bool(
                raw["connected"]
            )

        # --------------------------------------------------------------
        # Running / direction
        # --------------------------------------------------------------

        if "running" in raw:
            self.status.running = bool(
                raw["running"]
            )

        if "reverse" in raw:
            self.status.reverse = bool(
                raw["reverse"]
            )

        # --------------------------------------------------------------
        # Frequency
        #
        # Session currently exposes "frequency" and "target_frequency".
        # --------------------------------------------------------------

        frequency = raw.get(
            "frequency",
            raw.get(
                "target_frequency",
                self.status.frequency_hz,
            ),
        )

        try:
            self.status.frequency_hz = float(
                frequency
            )
        except (TypeError, ValueError):
            pass

        # --------------------------------------------------------------
        # RPM
        # --------------------------------------------------------------

        if "rpm" in raw:
            try:
                self.status.rpm = float(
                    raw["rpm"]
                )
            except (TypeError, ValueError):
                pass

        # --------------------------------------------------------------
        # Fault
        # --------------------------------------------------------------

        if "fault" in raw:
            self.status.fault = bool(
                raw["fault"]
            )

        if "fault_code" in raw:
            try:
                self.status.fault_code = int(
                    raw["fault_code"]
                )
            except (TypeError, ValueError):
                self.status.fault_code = None

        # --------------------------------------------------------------
        # Error
        #
        # Session currently calls this "error".
        # Manager exposes it as "last_error".
        # --------------------------------------------------------------

        session_error = raw.get(
            "error",
            "",
        )

        if session_error:
            self.status.last_error = str(
                session_error
            )
            self._last_error = (
                self.status.last_error
            )

        # --------------------------------------------------------------
        # State
        # --------------------------------------------------------------

        if self.status.fault:
            self.status.state = VFDState.FAULT

        elif not self.status.connected:
            self.status.state = (
                VFDState.DISCONNECTED
            )

        elif self.status.running:
            self.status.state = (
                VFDState.RUNNING
            )

        else:
            self.status.state = VFDState.READY

    # ==================================================================
    # PARAMETERS
    # ==================================================================

    def read_parameter(
        self,
        parameter: int,
    ):
        validated = self._validate_parameter(
            parameter,
            0,
        )

        if validated is None:
            return None

        parameter, _ = validated

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

        if result is None:
            self._set_error_from_session(
                "Parameter read failed."
            )

            return None

        self.clear_error()

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
            return self._set_error_from_session(
                "Parameter write failed."
            )

        self.clear_error()

        return True
