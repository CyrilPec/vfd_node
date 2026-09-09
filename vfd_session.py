from __future__ import annotations

import time
from typing import Optional

try:
    import serial
except ImportError:
    serial = None

from .hy01d523b_vfd import HY01D523B


class VFDSession:
    """
    Owns one physical VFD communication session.

    This is the only layer that should create/access the serial
    transport and HY01D523B driver.
    """

    def __init__(
        self,
        port: str = "COM3",
        slave_id: int = 4,
        baudrate: int = 9600,
        timeout: float = 0.25,
        status_interval: float = 0.2,
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

        self.last_status_time = 0.0
        self.last_error = ""

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def connect(self) -> bool:
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
                self.disconnect()
                return False

            self.last_error = ""
            self.last_status_time = 0.0
            return True

        except Exception as exc:
            self.last_error = (
                f"Serial connection failed: {exc}"
            )
            self.disconnect()
            return False

    def disconnect(self) -> None:
        driver = self.driver
        transport = self.transport

        self.driver = None
        self.transport = None

        if driver is not None:
            try:
                driver.disconnect()
                return
            except Exception:
                pass

        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

    def is_connected(self) -> bool:
        if self.driver is None:
            return False

        try:
            return bool(self.driver.is_connected())
        except Exception as exc:
            self.last_error = str(exc)
            return False

    # ------------------------------------------------------------------
    # STATUS RATE LIMIT
    # ------------------------------------------------------------------

    def should_poll_status(self) -> bool:
        now = time.monotonic()

        if (
            now - self.last_status_time
            < self.status_interval
        ):
            return False

        self.last_status_time = now
        return True

    def read_status(self):
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return None

        if not self.should_poll_status():
            return None

        try:
            return self.driver.read_control_status()

        except Exception as exc:
            self.last_error = str(exc)
            return None

    # ------------------------------------------------------------------
    # COMMANDS
    # ------------------------------------------------------------------

    def set_frequency(self, frequency_hz: float) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False

        try:
            result = self.driver.set_frequency(
                frequency_hz
            )

            if not result:
                self.last_error = (
                    getattr(
                        self.driver,
                        "last_error",
                        "",
                    )
                    or "Frequency command failed."
                )

            return bool(result)

        except Exception as exc:
            self.last_error = str(exc)
            return False

    def start(self, reverse: bool = False) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False

        try:
            if reverse:
                result = self.driver.reverse_run()
            else:
                result = self.driver.forward()

            if not result:
                self.last_error = (
                    getattr(
                        self.driver,
                        "last_error",
                        "",
                    )
                    or "Start command failed."
                )

            return bool(result)

        except Exception as exc:
            self.last_error = str(exc)
            return False

    def stop(self) -> bool:
        if not self.is_connected():
            self.last_error = "VFD is not connected."
            return False

        try:
            result = self.driver.stop()

            if not result:
                self.last_error = (
                    getattr(
                        self.driver,
                        "last_error",
                        "",
                    )
                    or "Stop command failed."
                )

            return bool(result)

        except Exception as exc:
            self.last_error = str(exc)
            return False
