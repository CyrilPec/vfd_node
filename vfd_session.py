from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    import serial
except ImportError:
    serial = None

from .hy01d523b_vfd import HY01D523B


@dataclass
class _Request:
    """
    Worker request.

    result/error are written by the worker and consumed by the
    caller for synchronous operations such as parameter access.
    """

    command: str
    args: tuple = ()
    kwargs: dict | None = None

    result: Any = None
    error: Optional[Exception] = None

    event: threading.Event | None = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}

        if self.event is None:
            self.event = threading.Event()


class VFDSession:
    """
    Single owner of the physical VFD connection.

    IMPORTANT:

        Only the worker thread is allowed to call HY01D523B.

    Blender/API/Manager communicate with this class through
    thread-safe methods.

    Architecture:

        Blender
           |
        VFDAPI
           |
        VFDManager
           |
        VFDSession
           |
        worker thread
           |
        HY01D523B
           |
        RS-485
    """

    DEFAULT_STATUS_INTERVAL = 0.2
    DEFAULT_TIMEOUT = 0.25

    PARAMETER_MIN = 0
    PARAMETER_MAX = 182

    def __init__(
        self,
        port: str = "COM3",
        slave_id: int = 4,
        baudrate: int = 9600,
        timeout: float = DEFAULT_TIMEOUT,
        status_interval: float = DEFAULT_STATUS_INTERVAL,
    ):
        self.port = str(port)
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.timeout = max(0.05, float(timeout))

        self.status_interval = max(
            0.05,
            float(status_interval),
        )

        # --------------------------------------------------------------
        # Hardware
        # --------------------------------------------------------------

        self.transport = None
        self.driver: Optional[HY01D523B] = None

        # --------------------------------------------------------------
        # Worker
        # --------------------------------------------------------------

        self._worker: Optional[threading.Thread] = None

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

        self._lock = threading.RLock()

        # Parameter requests are separate from continuous commands.
        self._request_queue: queue.Queue[
            _Request
        ] = queue.Queue(maxsize=32)

        # --------------------------------------------------------------
        # Latest desired commands.
        #
        # These are deliberately NOT a queue.
        #
        # If Blender changes 20 times while the worker is busy,
        # we only need the latest frequency/run/direction state.
        # --------------------------------------------------------------

        self._pending_frequency: Optional[float] = None
        self._pending_running: Optional[bool] = None
        self._pending_reverse: Optional[bool] = None

        # STOP is always explicit and has priority.
        self._stop_requested = False

        # --------------------------------------------------------------
        # Cached status
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

        self.last_error = ""

        self._last_status_time = 0.0

    # ==================================================================
    # CONNECTION
    # ==================================================================

    def connect(self) -> bool:
        """
        Explicit connection operation.

        This may block briefly because opening a serial port is not
        continuous node evaluation.

        After connection, all VFD I/O is worker-owned.
        """

        self.disconnect()

        if serial is None:
            self.last_error = (
                "pyserial is not installed."
            )
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

                self._close_hardware()
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

            self._close_hardware()

            return False

    def disconnect(self) -> None:
        """
        Stop the worker before destroying the hardware connection.
        """

        self._stop_worker()

        self._cancel_pending_requests(
            "VFD session disconnected."
        )

        self._close_hardware()

        with self._lock:
            self._status["connected"] = False
            self._status["running"] = False
            self._status["fault"] = False

    def _close_hardware(self) -> None:
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
        with self._lock:
            return bool(
                self._status["connected"]
            )

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
            name=(
                f"VFDWorker-{self.port}-"
                f"{self.slave_id}"
            ),
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
                    self.timeout * 4.0,
                )
            )

        self._worker = None

    def _worker_loop(self) -> None:
        """
        The ONLY place where driver communication happens.
        """

        next_status = time.monotonic()

        while not self._stop_event.is_set():

            did_work = False

            # ----------------------------------------------------------
            # 1. STOP has highest priority.
            # ----------------------------------------------------------

            if self._consume_stop():
                self._worker_stop()
                did_work = True

            # ----------------------------------------------------------
            # 2. Continuous commands.
            # ----------------------------------------------------------

            if self._process_pending_commands():
                did_work = True

            # ----------------------------------------------------------
            # 3. Explicit requests.
            #
            # Parameter read/write, etc.
            # ----------------------------------------------------------

            if self._process_request():
                did_work = True

            # ----------------------------------------------------------
            # 4. Periodic status polling.
            # ----------------------------------------------------------

            now = time.monotonic()

            if now >= next_status:
                self._worker_poll_status()

                next_status = (
                    now + self.status_interval
                )

                did_work = True

            # ----------------------------------------------------------
            # Avoid a busy loop.
            # ----------------------------------------------------------

            if not did_work:
                self._wake_event.wait(
                    timeout=0.01
                )

                self._wake_event.clear()

    # ==================================================================
    # CONTINUOUS COMMANDS
    # ==================================================================

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        """
        Queue latest frequency.

        Never performs hardware I/O.
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

        if (
            frequency_hz < 0.0
            or frequency_hz > 400.0
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
        Queue latest run/direction state.
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
        Queue high-priority stop.
        """

        with self._lock:
            self._stop_requested = True

            # A pending start must not survive a stop.
            self._pending_running = False
            self._pending_reverse = False

        self._wake_event.set()

        return True

    # ==================================================================
    # CONTINUOUS COMMAND PROCESSING
    # ==================================================================

    def _consume_stop(self) -> bool:
        with self._lock:
            if not self._stop_requested:
                return False

            self._stop_requested = False

        return True

    def _process_pending_commands(self) -> bool:
        did_work = False

        with self._lock:
            frequency = self._pending_frequency
            self._pending_frequency = None

            running = self._pending_running
            reverse = self._pending_reverse

            self._pending_running = None
            self._pending_reverse = None

        # Frequency first.
        if frequency is not None:
            self._worker_set_frequency(
                frequency
            )
            did_work = True

        # Then run/stop.
        if running is not None:
            if running:
                self._worker_start(
                    bool(reverse)
                )
            else:
                self._worker_stop()

            did_work = True

        return did_work

    # ==================================================================
    # HARDWARE COMMANDS
    # ==================================================================

    def _worker_set_frequency(
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

            self._clear_error()

            return True

        except Exception as exc:
            self._set_error(
                f"Frequency command failed: {exc}"
            )
            return False

    def _worker_start(
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

            self._clear_error()

            return True

        except Exception as exc:
            self._set_error(
                f"Start command failed: {exc}"
            )
            return False

    def _worker_stop(self) -> bool:

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

            self._clear_error()

            return True

        except Exception as exc:
            self._set_error(
                f"Stop command failed: {exc}"
            )
            return False

    # ==================================================================
    # EXPLICIT REQUESTS
    # ==================================================================

    def _submit_request(
        self,
        request: _Request,
        timeout: Optional[float] = None,
    ):
        """
        Put an explicit request into the worker queue.

        This is synchronous from the API caller's perspective, but
        the actual hardware operation happens exclusively in the
        worker thread.

        Therefore Blender never touches HY01D523B directly.
        """

        if not self.is_connected():
            self.last_error = (
                "VFD is not connected."
            )
            return None

        try:
            self._request_queue.put_nowait(
                request
            )

        except queue.Full:
            self.last_error = (
                "VFD request queue is full."
            )
            return None

        self._wake_event.set()

        wait_timeout = (
            self.timeout * 4.0
            if timeout is None
            else max(
                0.05,
                float(timeout),
            )
        )

        if not request.event.wait(
            timeout=wait_timeout
        ):
            self.last_error = (
                f"VFD request timed out: "
                f"{request.command}"
            )
            return None

        if request.error is not None:
            self.last_error = str(
                request.error
            )
            return None

        return request.result

    def _process_request(self) -> bool:
        try:
            request = (
                self._request_queue.get_nowait()
            )

        except queue.Empty:
            return False

        try:
            if request.command == "read_parameter":
                request.result = (
                    self._worker_read_parameter(
                        *request.args,
                        **request.kwargs,
                    )
                )

            elif request.command == "write_parameter":
                request.result = (
                    self._worker_write_parameter(
                        *request.args,
                        **request.kwargs,
                    )
                )

            else:
                raise ValueError(
                    f"Unknown VFD request: "
                    f"{request.command}"
                )

        except Exception as exc:
            request.error = exc

        finally:
            request.event.set()

        return True

    # ==================================================================
    # PARAMETER ACCESS
    # ==================================================================

    def read_parameter(
        self,
        parameter: int,
    ):
        try:
            parameter = int(parameter)
        except (TypeError, ValueError):
            self.last_error = (
                "Parameter must be an integer."
            )
            return None

        if not (
            self.PARAMETER_MIN
            <= parameter
            <= self.PARAMETER_MAX
        ):
            self.last_error = (
                f"Parameter must be between "
                f"{self.PARAMETER_MIN} and "
                f"{self.PARAMETER_MAX}."
            )
            return None

        request = _Request(
            command="read_parameter",
            args=(parameter,),
        )

        return self._submit_request(
            request
        )

    def write_parameter(
        self,
        parameter: int,
        value: int,
    ) -> bool:

        try:
            parameter = int(parameter)
            value = int(value)
        except (TypeError, ValueError):
            self.last_error = (
                "Parameter and value must be integers."
            )
            return False

        if not (
            self.PARAMETER_MIN
            <= parameter
            <= self.PARAMETER_MAX
        ):
            self.last_error = (
                f"Parameter must be between "
                f"{self.PARAMETER_MIN} and "
                f"{self.PARAMETER_MAX}."
            )
            return False

        if not (
            0 <= value <= 65535
        ):
            self.last_error = (
                "Parameter value must be "
                "between 0 and 65535."
            )
            return False

        request = _Request(
            command="write_parameter",
            args=(
                parameter,
                value,
            ),
        )

        result = self._submit_request(
            request
        )

        return bool(result)

    def _worker_read_parameter(
        self,
        parameter: int,
    ):

        driver = self.driver

        if driver is None:
            raise RuntimeError(
                "VFD is not connected."
            )

        return driver.read_parameter(
            parameter
        )

    def _worker_write_parameter(
        self,
        parameter: int,
        value: int,
    ) -> bool:

        driver = self.driver

        if driver is None:
            raise RuntimeError(
                "VFD is not connected."
            )

        result = driver.write_parameter(
            parameter,
            value,
        )

        return bool(result)

    # ==================================================================
    # STATUS POLLING
    # ==================================================================

    def _worker_poll_status(self) -> None:

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
                if isinstance(status, dict):
                    self._status.update(
                        status
                    )

                self._status[
                    "connected"
                ] = True

                self._last_status_time = (
                    time.monotonic()
                )

            self._clear_error()

        except Exception as exc:
            self._set_error(
                f"Status read failed: {exc}"
            )

    def get_status(self) -> dict:
        """
        Cached status only.

        No hardware access.
        """

        with self._lock:
            return dict(self._status)

    # ==================================================================
    # ERROR STATE
    # ==================================================================

    def _set_error(
        self,
        message: str,
    ) -> None:

        message = str(message)

        self.last_error = message

        with self._lock:
            self._status["error"] = message

    def _clear_error(self) -> None:
        self.last_error = ""

        with self._lock:
            self._status["error"] = ""

    # ==================================================================
    # CLEANUP
    # ==================================================================

    def _cancel_pending_requests(
        self,
        message: str,
    ) -> None:

        while True:
            try:
                request = (
                    self._request_queue.get_nowait()
                )

            except queue.Empty:
                break

            request.error = RuntimeError(
                message
            )

            request.event.set()
