"""
HY01D523B VFD serial driver.

This module contains NO Blender code.

Blender node -> driver -> pyserial -> RS485 -> HY01D523B
"""

import time
import threading

import serial


class HY01D523BError(Exception):
    pass


class HY01D523B:

    MODEL = "HY01D523B"
    SOFTWARE_VERSION = "1.00"

    DEFAULT_BAUDRATE = 9600
    DEFAULT_TIMEOUT = 0.25

    MIN_FREQUENCY = 0.0
    MAX_FREQUENCY = 400.0

    # Documented HY01D523B command frames.
    #
    # These are kept as protocol constants so they can be changed
    # independently of the Blender node.

    CMD_RUN = bytes.fromhex(
        "04 03 01 00 F0 84"
    )

    CMD_FORWARD = bytes.fromhex(
        "04 03 01 01 31 44"
    )

    CMD_REVERSE = bytes.fromhex(
        "04 03 01 02 71 45"
    )

    CMD_STOP = bytes.fromhex(
        "04 03 01 08 F1 42"
    )

    def __init__(
        self,
        port,
        slave_id=4,
        baudrate=9600,
        timeout=0.25,
    ):

        self.port = port
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)

        self.serial = None

        self.connected = False
        self.running = False
        self.reverse = False

        self.frequency_hz = 0.0

        self.last_response = b""
        self.last_error = ""

        self._lock = threading.Lock()

    # ------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------

    def connect(self):

        if self.connected:
            return True

        try:

            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )

            self.connected = True
            self.last_error = ""

            return True

        except Exception as exc:

            self.serial = None
            self.connected = False
            self.last_error = str(exc)

            return False

    def disconnect(self):

        try:

            if self.serial is not None:
                self.serial.close()

        except Exception:
            pass

        self.serial = None
        self.connected = False
        self.running = False

    # ------------------------------------------------------------
    # SERIAL
    # ------------------------------------------------------------

    def _write(self, data):

        if not self.connected or self.serial is None:
            raise HY01D523BError(
                "VFD is not connected."
            )

        with self._lock:

            try:

                self.serial.reset_input_buffer()

                self.serial.write(data)
                self.serial.flush()

            except Exception as exc:

                self.last_error = str(exc)

                raise HY01D523BError(
                    str(exc)
                )

    def _read(self, minimum_bytes=1):

        if not self.connected or self.serial is None:
            raise HY01D523BError(
                "VFD is not connected."
            )

        data = bytearray()

        deadline = (
            time.monotonic()
            + self.timeout
        )

        while time.monotonic() < deadline:

            waiting = self.serial.in_waiting

            if waiting:

                data.extend(
                    self.serial.read(waiting)
                )

                if len(data) >= minimum_bytes:
                    break

            else:

                time.sleep(0.005)

        self.last_response = bytes(data)

        return self.last_response

    def send(self, frame, read_response=False):

        self._write(frame)

        if read_response:
            return self._read()

        return b""

    # ------------------------------------------------------------
    # FREQUENCY
    # ------------------------------------------------------------

    def set_frequency(self, frequency_hz):

        frequency_hz = float(frequency_hz)

        frequency_hz = max(
            self.MIN_FREQUENCY,
            min(
                self.MAX_FREQUENCY,
                frequency_hz,
            ),
        )

        value = int(
            round(frequency_hz * 100.0)
        )

        # HY01D523B documented frequency frame:
        #
        # 04 05 02 HH LL CRC
        #
        # Frequency is Hz * 100.

        frame = bytes(
            (
                self.slave_id,
                0x05,
                0x02,
                (value >> 8) & 0xFF,
                value & 0xFF,
            )
        )

        frame += self.crc16(frame)

        self.send(frame)

        self.frequency_hz = frequency_hz

        return True

    # ------------------------------------------------------------
    # RUN / STOP
    # ------------------------------------------------------------

    def run(self):

        self.send(self.CMD_RUN)

        self.running = True
        self.reverse = False

        return True

    def forward(self):

        self.send(self.CMD_FORWARD)

        self.running = True
        self.reverse = False

        return True

    def reverse_run(self):

        self.send(self.CMD_REVERSE)

        self.running = True
        self.reverse = True

        return True

    def stop(self):

        self.send(self.CMD_STOP)

        self.running = False

        return True

    # ------------------------------------------------------------
    # HIGH LEVEL COMMAND
    # ------------------------------------------------------------

    def apply_command(
        self,
        run,
        reverse,
        frequency,
    ):

        self.set_frequency(frequency)

        if run:

            if reverse:
                self.reverse_run()
            else:
                self.forward()

        else:

            self.stop()

        return True

    # ------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------

    def get_status(self):

        return {
            "connected": self.connected,
            "running": self.running,
            "reverse": self.reverse,
            "frequency": self.frequency_hz,
            "fault": False,
            "fault_code": 0,
            "error": self.last_error,
        }

    # ------------------------------------------------------------
    # CRC16
    # ------------------------------------------------------------

    @staticmethod
    def crc16(data):

        crc = 0xFFFF

        for byte in data:

            crc ^= byte

            for _ in range(8):

                if crc & 1:

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
