"""
Huanyang HY01D523B VFD driver.

Communication:
    RS-485
    8N1
    Default baudrate: 9600

The serial transport is injected so the driver can be tested
without requiring real hardware.
"""

from __future__ import annotations

import threading
import time


class HY01D523BError(Exception):
    """HY01D523B driver error."""


class HY01D523B:
    MODEL = "HY01D523B"
    SOFTWARE_VERSION = "1.20"

    DEFAULT_BAUDRATE = 9600
    DEFAULT_BYTESIZE = 8
    DEFAULT_PARITY = "N"
    DEFAULT_STOPBITS = 1

    MIN_FREQUENCY = 0.0
    MAX_FREQUENCY = 400.0

    MIN_PARAMETER = 0
    MAX_PARAMETER = 182

    # HY01D523B control frames for slave 04.
    # Address is replaced with self.slave_id below.
    CMD_FORWARD = bytes.fromhex(
        "04 03 01 01 31 44"
    )

    CMD_REVERSE = bytes.fromhex(
        "04 03 01 02 71 45"
    )

    CMD_STOP = bytes.fromhex(
        "04 03 01 08 F1 42"
    )

    CMD_RUN = bytes.fromhex(
        "04 03 01 00 F0 84"
    )

    def __init__(
        self,
        serial_port=None,
        slave_id=4,
        baudrate=DEFAULT_BAUDRATE,
        timeout=0.25,
    ):
        self.serial = serial_port

        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)

        self.connected = False

        # Locally tracked command state.
        self.running = False
        self.reverse = False
        self.frequency_hz = 0.0

        self.last_error = ""
        self.last_response = b""

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def connect(self):
        """
        Open the injected serial transport.

        The transport must provide:
            open()
            close()
            is_open
            write()
            read()
            in_waiting
            reset_input_buffer()
        """

        if self.serial is None:
            self.last_error = (
                "No serial transport supplied."
            )
            return False

        try:
            if hasattr(self.serial, "is_open"):
                if not self.serial.is_open:
                    self.serial.open()
            else:
                self.serial.open()

            self.connected = True
            self.last_error = ""

            return True

        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            return False

    def disconnect(self):
        try:
            if self.serial is not None:
                self.serial.close()
        except Exception:
            pass

        self.connected = False
        self.running = False

    def is_connected(self):
        if not self.connected:
            return False

        if self.serial is None:
            return False

        if hasattr(self.serial, "is_open"):
            return bool(self.serial.is_open)

        return True

    # ------------------------------------------------------------------
    # RAW TRANSPORT
    # ------------------------------------------------------------------

    def _write_raw(self, frame):
        if not self.is_connected():
            raise HY01D523BError(
                "VFD is not connected."
            )

        with self._lock:
            try:
                if hasattr(
                    self.serial,
                    "reset_input_buffer",
                ):
                    self.serial.reset_input_buffer()

                written = self.serial.write(frame)

                if written is not None:
                    if int(written) != len(frame):
                        raise HY01D523BError(
                            f"Serial write incomplete: "
                            f"{written}/{len(frame)} bytes."
                        )

                if hasattr(
                    self.serial,
                    "flush",
                ):
                    self.serial.flush()

                self.last_response = b""

            except Exception as exc:
                self.last_error = str(exc)
                raise HY01D523BError(str(exc))

    def _read_response(
        self,
        size,
    ):
        if not self.is_connected():
            raise HY01D523BError(
                "VFD is not connected."
            )

        deadline = (
            time.monotonic()
            + self.timeout
        )

        data = bytearray()

        while (
            time.monotonic()
            < deadline
        ):
            try:
                waiting = int(
                    getattr(
                        self.serial,
                        "in_waiting",
                        0,
                    )
                )
            except Exception:
                waiting = 0

            if waiting > 0:
                chunk = self.serial.read(
                    min(
                        waiting,
                        size - len(data),
                    )
                )

                if chunk:
                    data.extend(chunk)

                    if len(data) >= size:
                        break

            else:
                time.sleep(0.002)

        self.last_response = bytes(data)

        return self.last_response

    def _send(
        self,
        frame,
        expect_response=False,
        response_size=0,
    ):
        self._write_raw(frame)

        if not expect_response:
            return b""

        return self._read_response(
            response_size
        )

    # ------------------------------------------------------------------
    # CONTROL COMMANDS
    # ------------------------------------------------------------------

    def _control_frame(self, command):
        """
        Replace the address byte in the documented control frame
        with the configured slave address and recalculate CRC.
        """

        body = bytes(
            (
                self.slave_id,
                command[1],
                command[2],
                command[3],
            )
        )

        return body + self._crc16_modbus(
            body
        )

    def forward(self):
        frame = self._control_frame(
            self.CMD_FORWARD
        )

        self._send(frame)

        self.running = True
        self.reverse = False
        self.last_error = ""

        return True

    def reverse_run(self):
        frame = self._control_frame(
            self.CMD_REVERSE
        )

        self._send(frame)

        self.running = True
        self.reverse = True
        self.last_error = ""

        return True

    def stop(self):
        frame = self._control_frame(
            self.CMD_STOP
        )

        self._send(frame)

        self.running = False
        self.last_error = ""

        return True

    def run(self):
        frame = self._control_frame(
            self.CMD_RUN
        )

        self._send(frame)

        self.running = True
        self.reverse = False
        self.last_error = ""

        return True

    # ------------------------------------------------------------------
    # FREQUENCY
    # ------------------------------------------------------------------

    def set_frequency(self, frequency_hz):
        try:
            frequency_hz = float(
                frequency_hz
            )
        except (TypeError, ValueError):
            raise HY01D523BError(
                "Invalid frequency."
            )

        if (
            frequency_hz
            < self.MIN_FREQUENCY
            or frequency_hz
            > self.MAX_FREQUENCY
        ):
            raise HY01D523BError(
                f"Frequency must be between "
                f"{self.MIN_FREQUENCY:.2f} and "
                f"{self.MAX_FREQUENCY:.2f} Hz."
            )

        value = int(
            round(
                frequency_hz * 100.0
            )
        )

        if value > 0xFFFF:
            raise HY01D523BError(
                "Frequency value exceeds 16-bit range."
            )

        body = bytes(
            (
                self.slave_id,
                0x05,
                0x02,
                (value >> 8) & 0xFF,
                value & 0xFF,
            )
        )

        frame = (
            body
            + self._crc16_modbus(body)
        )

        self._send(frame)

        self.frequency_hz = frequency_hz
        self.last_error = ""

        return True

    # ------------------------------------------------------------------
    # PARAMETERS
    # ------------------------------------------------------------------

    def _validate_parameter(
        self,
        parameter,
    ):
        try:
            parameter = int(
                parameter
            )
        except (TypeError, ValueError):
            raise ValueError(
                "Parameter must be an integer."
            )

        if not (
            self.MIN_PARAMETER
            <= parameter
            <= self.MAX_PARAMETER
        ):
            raise ValueError(
                f"Parameter must be between "
                f"PD{self.MIN_PARAMETER:03d} "
                f"and PD{self.MAX_PARAMETER:03d}."
            )

        return parameter

    def read_parameter(
        self,
        parameter,
    ):
        parameter = self._validate_parameter(
            parameter
        )

        address = self.slave_id

        body = bytes(
            (
                address,
                0x01,
                0x03,
                (parameter >> 8) & 0xFF,
                parameter & 0xFF,
                0x00,
                0x00,
            )
        )

        frame = (
            body
            + self._crc16_modbus(body)
        )

        response = self._send(
            frame,
            expect_response=True,
            response_size=9,
        )

        if len(response) != 9:
            raise HY01D523BError(
                f"Invalid response length reading "
                f"PD{parameter:03d}: "
                f"{response.hex(' ')}"
            )

        if response[0] != address:
            raise HY01D523BError(
                f"Wrong VFD address: "
                f"{response[0]:02X}, "
                f"expected {address:02X}."
            )

        # Exception response.
        if response[1] & 0x80:
            raise HY01D523BError(
                f"VFD returned exception: "
                f"function={response[1]:02X}, "
                f"code={response[2]:02X}"
            )

        if response[1] != 0x01:
            raise HY01D523BError(
                f"Unexpected response function: "
                f"{response[1]:02X}"
            )

        if response[2] != 0x02:
            raise HY01D523BError(
                f"Unexpected response data length: "
                f"{response[2]:02X}"
            )

        expected_crc = self._crc16_modbus(
            response[:7]
        )

        received_crc = response[7:9]

        if received_crc != expected_crc:
            raise HY01D523BError(
                f"Invalid CRC reading "
                f"PD{parameter:03d}: "
                f"{response.hex(' ')}"
            )

        returned_parameter = (
            response[3] << 8
        ) | response[4]

        if returned_parameter != parameter:
            raise HY01D523BError(
                f"VFD returned "
                f"PD{returned_parameter:03d}, "
                f"expected PD{parameter:03d}."
            )

        value = (
            response[5] << 8
        ) | response[6]

        self.last_error = ""

        return value

    def write_parameter(
        self,
        parameter,
        value,
    ):
        parameter = self._validate_parameter(
            parameter
        )

        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError(
                "Parameter value must be an integer."
            )

        if not 0 <= value <= 0xFFFF:
            raise ValueError(
                "Parameter value must be between "
                "0 and 65535."
            )

        body = bytes(
            (
                self.slave_id,
                0x02,
                0x03,
                (parameter >> 8) & 0xFF,
                parameter & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            )
        )

        frame = (
            body
            + self._crc16_modbus(body)
        )

        self._send(frame)

        self.last_error = ""

        return True

    # ------------------------------------------------------------------
    # CRC
    # ------------------------------------------------------------------

    @staticmethod
    def _crc16_modbus(data):
        crc = 0xFFFF

        for byte in data:
            crc ^= byte

            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1

        return bytes(
            (
                crc & 0xFF,
                (crc >> 8) & 0xFF,
            )
        )

    # ------------------------------------------------------------------
    # HIGH-LEVEL COMMAND
    # ------------------------------------------------------------------

    def command(
        self,
        run=False,
        reverse=False,
        frequency=None,
    ):
        if frequency is not None:
            self.set_frequency(
                frequency
            )

        if run:
            if reverse:
                self.reverse_run()
            else:
                self.forward()
        else:
            self.stop()

        return True

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_local_status(self):
        """
        Return locally tracked status.

        IMPORTANT:
        This is not a hardware status-word read.

        running/reverse/frequency describe the last commands
        accepted by this software layer. They should not be
        interpreted as measured spindle RPM or confirmed VFD
        operating state.
        """

        return {
            "connected": self.is_connected(),
            "running": self.running,
            "reverse": self.reverse,
            "frequency": self.frequency_hz,
            "fault": False,
            "fault_code": 0,
            "error": self.last_error,
        }
