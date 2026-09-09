from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import serial
except ImportError:
    serial = None

from .hy01d523b_vfd import HY01D523B


@dataclass
class _Command:
    name: str
    value: object = None


class VFDSession:
    """
    Owns one physical VFD connection.

    Blender never performs serial I/O directly.

    Public flow:

        Blender
            ↓
        VFDManager
            ↓
        VFDSession
            ↓
        worker thread
            ↓
        HY01D523B
            ↓
        RS-485
    """

    DEFAULT_STATUS_INTERVAL = 0.2      # 5 Hz
    DEFAULT_COMMAND_WAIT = 0.01
    MAX_COMMANDS = 32

    def __init__(
        self,
        port: str = "COM3",
        slave_id: int = 4,
        baudrate: int = 9600,
        timeout: float = 0.25,
        status_interval: float = DEFAULT_STATUS_INTERVAL,
    ):
        self.port = str(port)
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)

        self.status_interval = max(
            0.05,
            float(status_interval),
        )

        self.transport = None
        self.driver: Optional[HY01D523B] = None

        # --------------------------------------------------------------
        # Worker
        # --------------------------------------------------------------

        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

        self._lock = threading.RLock()

        # Only the latest frequency matters.
        self._pending_frequency: Optional[float] = None

        # Run/direction are state transitions.
        self._pending_running: Optional[bool] = None
        self._pending_reverse: Optional[bool] = None

        # STOP gets explicit priority.
        self._stop_requested = False

        # --------------------------------------------------------------
        # Cached state
        # --------------------------------------------------------------

        self._status = {
            "connected": False,
            "running": False,
            "reverse": False,
            "frequency": 0.0,
            "target_frequency": 0.0,
            "output_frequency": 0.0,
            "rpm": 0.0,
            "fault": False,
            "fault_code": 0,
            "error": "",
        }

        self._last_status_time = 0.0

        self.last_error = ""

    # ==================================================================
    # CONNECTION
    # ==================================================================

    def connect(self) -> bool:
        """
        Connect synchronously.

        Connection itself is intentionally synchronous because Blender
        should call this only from an explicit Connect operation, not
        from node evaluation.
        """

        self.disconnect()

        if serial is None:
            self.last_error = "pyserial is not installed."
            return False

        try:
            self.transport = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )

            self.driver = HY01D523B(
                serial_port=self.transport,
                slave_id=self.slave_id,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )

            if not self.driver.connect():
                self.last_error = (
                    getattr(
                        self.driver,
                        "last_error",
                        "",
                    )
                    or "VFD connection failed."
                )

                self._close_transport()
                return False

            self.last_error = ""

            with self._lock:
                self._status["connected"] = True
                self._status["error"] = ""

            self._start_worker()

            return True

        except Exception as exc:
            self.last_error = (
                f"Serial connection failed: {exc}"
            )

            self._close_transport()

            return False

    def disconnect(self) -> None:
        """
        Stop worker first, then close the driver/serial port.
        """

        self._stop_worker()

        driver = self.driver
        transport = self.transport

        self.driver = None
        self.transport = None

        if driver is not None:
            try:
                driver.disconnect()
            except Exception:
                pass

        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

        with self._lock:
            self._status["connected"] = False
            self._status["running"] = False

    def _close_transport(self) -> None:
        driver = self.driver
        transport = self.transport

        self.driver = None
        self.transport = None

        if driver is not None:
            try:
                driver.disconnect()
            except Exception:
                pass

        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

    def is_connected(self) -> bool:
        driver = self.driver

        if driver is None:
            return False

        try:
            return bool(
                driver.is_connected()
            )
        except Exception as exc:
            self.last_error = str(exc)
            return False

    # ==================================================================
    # WORKER
    # ==================================================================

    def _start_worker(self) -> None:
        if (
            self._worker is not None
            and self._worker.is_alive()
        ):
            return

        self._stop_event.clear()
        self._wake_event.clear()

        self._worker = threading.Thread(
            target=self._worker_loop,
            name=f"VFD-{self.port}-{self.slave_id}",
            daemon=True,
        )

        self._worker.start()

    def _stop_worker(self) -> None:
        worker = self._worker

        if worker is None:
            return

        self._stop_event.set()
        self._wake_event.set()

        if (
            worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(
                timeout=max(
                    1.0,
                    self.timeout + 0.5,
                )
            )

        self._worker = None

    def _worker_loop(self) -> None:
        """
        Only this thread performs VFD communication.
        """

        next_status = time.monotonic()

        while not self._stop_event.is_set():

            did_work = False

            # ----------------------------------------------------------
            # STOP has highest priority.
            # ----------------------------------------------------------

            if self._consume_stop():
                self._execute_stop()
                did_work = True

            # ----------------------------------------------------------
            # Commands.
            # ----------------------------------------------------------

            if self._process_pending_commands():
                did_work = True

            # ----------------------------------------------------------
            # Status polling.
            # ----------------------------------------------------------

            now = time.monotonic()

            if now >= next_status:
                self._poll_status()

                next_status = (
                    now + self.status_interval
                )

                did_work = True

            # ----------------------------------------------------------
            # Don't spin the CPU.
            # ----------------------------------------------------------

            if not did_work:
                self._wake_event.wait(
                    timeout=self.DEFAULT_COMMAND_WAIT
                )

                self._wake_event.clear()

    # ==================================================================
    # COMMAND QUEUE
    # ==================================================================

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        """
        Queue a frequency command.

        This does NOT touch the serial port.
        """

        try:
            frequency_hz = float(
                frequency_hz
            )
        except (TypeError, ValueError):
            self.last_error = (
                "Frequency must be numeric."
            )
            return False

        if not (
            0.0
            <= frequency_hz
            <= 400.0
        ):
            self.last_error = (
                "Frequency must be between "
                "0 and 400 Hz."
            )
            return False

        with self._lock:
            self._pending_frequency = (
                frequency_hz
            )

        self._wake_event.set()

        return True

    def start(
        self,
        reverse: bool = False,
    ) -> bool:
        """
        Queue RUN.

        The worker performs the actual serial operation.
        """

        with self._lock:
            self._pending_running = True
            self._pending_reverse = bool(
                reverse
            )

        self._wake_event.set()

        return True

    def stop(self) -> bool:
        """
        Queue a high-priority STOP.
        """

        with self._lock:
            self._stop_requested = True

            # A stop supersedes a pending run.
            self._pending_running = False

        self._wake_event.set()

        return True

    # ==================================================================
    # COMMAND PROCESSING
    # ==================================================================

    def _consume_stop(self) -> bool:
        with self._lock:
            if not self._stop_requested:
                return False

            self._stop_requested = False

        return True

    def _process_pending_commands(self) -> bool:
        did_work = False

        # --------------------------------------------------------------
        # Frequency
        # --------------------------------------------------------------

        with self._lock:
            frequency = (
                self._pending_frequency
            )
            self._pending_frequency = None

        if frequency is not None:
            if self._execute_frequency(
                frequency
            ):
                did_work = True

        # --------------------------------------------------------------
        # Run / direction
        # --------------------------------------------------------------

        with self._lock:
            running = (
                self._pending_running
            )
            reverse = (
                self._pending_reverse
            )

            self._pending_running = None
            self._pending_reverse = None

        if running is not None:

            if running:
                if self._execute_start(
                    bool(reverse)
                ):
                    did_work = True
            else:
                if self._execute_stop():
                    did_work = True

        return did_work

    # ==================================================================
    # HARDWARE OPERATIONS
    # ==================================================================

    def _execute_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        driver = self.driver

        if driver is None:
            self._set_error(
                "VFD is not connected."
            )
            return False

        try:
            driver.set_frequency(
                frequency_hz
            )

            with self._lock:
                self._status[
                    "target_frequency"
                ] = frequency_hz

                self._status[
                    "frequency"
                ] = frequency_hz

                self._status["error"] = ""

            return True

        except Exception as exc:
            self._set_error(
                f"Frequency command failed: {exc}"
            )

            return False

    def _execute_start(
        self,
        reverse: bool,
    ) -> bool:
        driver = self.driver

        if driver is None:
            self._set_error(
                "VFD is not connected."
            )
            return False

        try:
            if reverse:
                driver.reverse_run()
            else:
                driver.forward()

            with self._lock:
                self._status["running"] = True
                self._status["reverse"] = bool(
                    reverse
                )
                self._status["error"] = ""

            return True

        except Exception as exc:
            self._set_error(
                f"Start command failed: {exc}"
            )

            return False

    def _execute_stop(self) -> bool:
        driver = self.driver

        if driver is None:
            self._set_error(
                "VFD is not connected."
            )
            return False

        try:
            driver.stop()

            with self._lock:
                self._status["running"] = False
                self._status["error"] = ""

            return True

        except Exception as exc:
            self._set_error(
                f"Stop command failed: {exc}"
            )

            return False

    # ==================================================================
    # STATUS
    # ==================================================================

    def _poll_status(self) -> None:
        driver = self.driver

        if driver is None:
            return

        try:
            status = (
                driver.read_control_status()
            )

            if status is None:
                return

            with self._lock:
                self._status.update(status)

                self._status[
                    "connected"
                ] = bool(
                    driver.is_connected()
                )

                self._status[
                    "error"
                ] = self.last_error

                self._last_status_time = (
                    time.monotonic()
                )

        except Exception as exc:
            self._set_error(
                f"Status read failed: {exc}"
            )

    def get_status(self) -> dict:
        """
        Return cached status.

        NO hardware I/O.
        """

        with self._lock:
            return dict(self._status)

    # ==================================================================
    # PARAMETERS
    # ==================================================================

    def read_parameter(
        self,
        parameter: int,
    ):
        """
        Parameter operations are explicit requests.

        They are executed in the worker so Blender doesn't block.
        """

        try:
            parameter = int(parameter)
        except (TypeError, ValueError):
            self.last_error = (
                "Parameter must be an integer."
            )
            return None

        # This is intentionally a synchronous API for now.
        #
        # The next iteration can make parameter reads fully
        # asynchronous with a Future/result object.
        driver = self.driver

        if driver is None:
            self._set_error(
                "VFD is not connected."
            )
            return None

        try:
            return driver.read_parameter(
                parameter
            )

        except Exception as exc:
            self._set_error(
                f"Parameter read failed: {exc}"
            )
            return None

    def write_parameter(
        self,
        parameter: int,
        value: int,
    ) -> bool:
        try:
            parameter = int(parameter)
            value = int(value)
        except (TypeError, ValueError):
            self._set_error(
                "Parameter and value must be integers."
            )
            return False

        if not (
            0 <= parameter <= 182
        ):
            self._set_error(
                "Parameter must be PD000..PD182."
            )
            return False

        if not (
            0 <= value <= 65535
        ):
            self._set_error(
                "Parameter value must be "
                "between 0 and 65535."
            )
            return False

        driver = self.driver

        if driver is None:
            self._set_error(
                "VFD is not connected."
            )
            return False

        try:
            driver.write_parameter(
                parameter,
                value,
            )

            self.last_error = ""

            return True

        except Exception as exc:
            self._set_error(
                f"Parameter write failed: {exc}"
            )
            return False

    # ==================================================================
    # ERROR
    # ==================================================================

    def _set_error(
        self,
        message: str,
    ) -> None:
        self.last_error = str(message)

        with self._lock:
            self._status["error"] = (
                self.last_error
            )
