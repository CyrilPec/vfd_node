"""
Huanyang HY01D523B VFD driver
Firmware reference: PD181 = U-1.00

This driver implements the command protocol documented for the
HY01D523B family.

Serial:
    RS-485
    Modbus RTU-style framing
    Default documented communication:
        9600 baud
        8N1
        slave address configured by PD163

Important:
    The HY01D523B command protocol is NOT the same as the newer
    Huanyang 0x2000/0x2001 style protocol.

Tested/documented command examples:

    Forward:  04 03 01 01 31 44
    Stop:     04 03 01 08 F1 42
    Reverse:  04 03 01 02 71 45

Frequency:
    10.00 Hz -> 03 E8
    50.00 Hz -> 13 88
    400.00 Hz -> 9C 40

Therefore:
    frequency_register_value = frequency_hz * 100
"""

from __future__ import annotations

import time
import threading


class HY01D523BError(Exception):
    """HY01D523B driver error."""
    pass


class HY01D523B:
    """
    Low-level HY01D523B driver.

    The serial object is deliberately injected so that this class
    does not depend on a particular RS-485 library.
    """

    MODEL = "HY01D523B"
    SOFTWARE_VERSION = "1.00"

    DEFAULT_BAUDRATE = 9600
    DEFAULT_BYTESIZE = 8
    DEFAULT_PARITY = "N"
    DEFAULT_STOPBITS = 1

    MIN_FREQUENCY = 0.0
    MAX_FREQUENCY = 400.0

    # ------------------------------------------------------------------
    # HY01D523B control commands
    # ------------------------------------------------------------------

    CMD_FORWARD = bytes.fromhex("04 03 01 01 31 44")
    CMD_REVERSE = bytes.fromhex("04 03 01 02 71 45")
    CMD_STOP = bytes.fromhex("04 03 01 08 F1 42")
    CMD_RUN = bytes.fromhex("04 03 01 00 F0 84")

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
            reset_input_buffer()
        """

        if self.serial is None:
            self.last_error = "No serial transport supplied."
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
            raise HY01D523BError("VFD is not connected.")

        with self._lock:
            try:
                if hasattr(self.serial, "reset_input_buffer"):
                    self.serial.reset_input_buffer()

                self.serial.write(frame)

                if hasattr(self.serial, "flush"):
                    self.serial.flush()

                self.last_response = b""
                return True

            except Exception as exc:
                self.last_error = str(exc)
                raise HY01D523BError(str(exc))

    def _read_response(self, size=8):
        if not self.is_connected():
            raise HY01D523BError("VFD is not connected.")

        deadline = time.monotonic() + self.timeout
        data = bytearray()

        while time.monotonic() < deadline:
            waiting = 0

            try:
                waiting = int(getattr(self.serial, "in_waiting", 0))
            except Exception:
                waiting = 0

            if waiting:
                chunk = self.serial.read(waiting)
                if chunk:
                    data.extend(chunk)

                    if len(data) >= size:
                        break

            else:
                time.sleep(0.005)

        self.last_response = bytes(data)

        return self.last_response

    def _send(self, frame, expect_response=False, response_size=8):
        self._write_raw(frame)

        if not expect_response:
            return b""

        return self._read_response(response_size)

    # ------------------------------------------------------------------
    # CONTROL
    # ------------------------------------------------------------------

    def forward(self):
        """
        Forward run command.
        """
        self._send(self.CMD_FORWARD)

        self.running = True
        self.reverse = False

        return True

    def reverse_run(self):
        """
        Reverse run command.
        """
        self._send(self.CMD_REVERSE)

        self.running = True
        self.reverse = True

        return True

    def stop(self):
        """
        Stop command.
        """
        self._send(self.CMD_STOP)

        self.running = False

        return True

    def run(self):
        """
        Normal forward RUN command.
        """
        self._send(self.CMD_RUN)

        self.running = True
        self.reverse = False

        return True

    # ------------------------------------------------------------------
    # FREQUENCY
    # ------------------------------------------------------------------

    def set_frequency(self, frequency_hz):
        """
        Set operating frequency.

        HY01D523B uses frequency * 100.

        Example:
            10.00 Hz -> 1000 -> 0x03E8
            50.00 Hz -> 5000 -> 0x1388
        """

        frequency_hz = float(frequency_hz)

        if frequency_hz < self.MIN_FREQUENCY:
            frequency_hz = self.MIN_FREQUENCY

        if frequency_hz > self.MAX_FREQUENCY:
            frequency_hz = self.MAX_FREQUENCY

        value = int(round(frequency_hz * 100.0))

        if value > 0xFFFF:
            raise HY01D523BError(
                "Frequency value exceeds 16-bit range."
            )

        # The documented HY01D523B frequency command is:
        #
        # 04 05 02 HH LL CRC_L CRC_H
        #
        # 04 = VFD address in documented examples
        # 05 = frequency command
        # 02 = frequency data length
        # HH LL = frequency * 100

        address = self.slave_id

        frame_without_crc = bytes(
            (
                address,
                0x05,
                0x02,
                (value >> 8) & 0xFF,
                value & 0xFF,
            )
        )

        frame = frame_without_crc + self._crc16_modbus(
            frame_without_crc
        )

        self._send(frame)

        self.frequency_hz = frequency_hz

        return True

    # ------------------------------------------------------------------
    # READ PARAMETER
    # ------------------------------------------------------------------

    def read_parameter(self, parameter):
        """
        Read one PD parameter.

        Example:
            read_parameter(163)

        PD163 = communication address
        PD164 = baud setting
        PD165 = communication data method
        PD181 = software version
        """

        parameter = int(parameter)

        if parameter < 0 or parameter > 250:
            raise ValueError("Parameter must be between 0 and 250.")

        address = self.slave_id

        frame_without_crc = bytes(
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

        frame = frame_without_crc + self._crc16_modbus(
            frame_without_crc
        )

        response = self._send(
            frame,
            expect_response=True,
            response_size=8,
        )

        if len(response) < 5:
            raise HY01D523BError(
                "Invalid parameter response: "
                + response.hex(" ")
            )

        return response

    # ------------------------------------------------------------------
    # WRITE PARAMETER
    # ------------------------------------------------------------------

    def write_parameter(self, parameter, value):
        """
        Write a PD parameter.

        This uses the documented HY01D523B write format:

            address 02 03 parameter_hi parameter_lo
            value_hi value_lo CRC
        """

        parameter = int(parameter)
        value = int(value)

        if not 0 <= parameter <= 250:
            raise ValueError("Parameter must be between 0 and 250.")

        if not 0 <= value <= 0xFFFF:
            raise ValueError("Parameter value must be 0..65535.")

        frame_without_crc = bytes(
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

        frame = frame_without_crc + self._crc16_modbus(
            frame_without_crc
        )

        self._send(frame)

        return True

    # ------------------------------------------------------------------
    # CRC
    # ------------------------------------------------------------------

    @staticmethod
    def _crc16_modbus(data):
        """
        Return Modbus CRC as little-endian bytes.
        """

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
    # HIGH LEVEL COMMAND
    # ------------------------------------------------------------------

    def command(
        self,
        run=False,
        reverse=False,
        frequency=None,
    ):
        """
        Apply a complete VFD command.

        Frequency is sent first, then run direction.
        """

        if frequency is not None:
            self.set_frequency(frequency)

        if run:
            if reverse:
                self.reverse_run()
            else:
                self.run()
        else:
            self.stop()

        return True

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_local_status(self):
        """
        Return locally tracked status.

        The current public HY01D523B protocol information does not
        give us enough confidence to invent a status-word register,
        so this deliberately does not pretend to decode one.
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
