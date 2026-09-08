from __future__ import annotations

from vfd_protocol import VFDProtocol


class HY01D523B:
    """
    Huanyang HY01D523B driver.

    This class contains VFD-specific protocol knowledge.
    It should not contain high-level CNC logic.
    """

    CMD_FORWARD = 0x01
    CMD_REVERSE = 0x02
    CMD_STOP = 0x08

    MIN_FREQUENCY_HZ = 0.0
    MAX_FREQUENCY_HZ = 400.0

    def __init__(
        self,
        transport,
        slave_id: int = 4,
    ):
        self.protocol = VFDProtocol(
            transport=transport,
            slave_id=slave_id,
        )

    def _command(self, command: int) -> bytes:
        payload = bytes([
            self.protocol.slave_id,
            0x03,
            0x01,
            command,
        ])

        return self.protocol.transaction(payload)

    def forward(self) -> bytes:
        return self._command(self.CMD_FORWARD)

    def reverse(self) -> bytes:
        return self._command(self.CMD_REVERSE)

    def stop(self) -> bytes:
        return self._command(self.CMD_STOP)

    def set_frequency(self, frequency_hz: float) -> bytes:
        if not (
            self.MIN_FREQUENCY_HZ
            <= frequency_hz
            <= self.MAX_FREQUENCY_HZ
        ):
            raise ValueError(
                f"Frequency {frequency_hz} Hz outside "
                f"{self.MIN_FREQUENCY_HZ}.."
                f"{self.MAX_FREQUENCY_HZ} Hz"
            )

        # This part must match the exact HY01D523B protocol.
        # Keep it isolated here.
        value = round(frequency_hz * 100)

        high = (value >> 8) & 0xFF
        low = value & 0xFF

        payload = bytes([
            self.protocol.slave_id,
            0x03,
            0x02,
            high,
            low,
        ])

        return self.protocol.transaction(payload)

 class HY01D523B:
    # ...

    def read_status(self) -> dict:
        """
        Read actual VFD operating data.
        """

        # The register/frame details should be verified against
        # the exact VFD firmware before hardware deployment.

        response = self.protocol.transaction(
            bytes([
                self.protocol.slave_id,
                0x03,
                0x00,
                0x00,
            ])
        )

        return self._parse_status(response)

    def _parse_status(self, response: bytes) -> dict:
        # Decode actual VFD response here.
        raise NotImplementedError
 import time

from vfd_status import VFDState


class SpindleController:

    STOP_CONFIRM_SAMPLES = 6
    STOP_FREQUENCY_THRESHOLD = 0.5

    def __init__(self, driver):
        self.driver = driver

        self.state = VFDState.IDLE

        self.stop_samples = 0

        self.commanded_running = False
        self.commanded_reverse = False
        self.commanded_frequency_hz = 0.0

        self.actual_frequency_hz = 0.0
        self.actual_rpm = 0.0

    def start_forward(self):
        self.driver.forward()

        self.commanded_running = True
        self.commanded_reverse = False
        self.state = VFDState.STARTING

    def start_reverse(self):
        self.driver.reverse()

        self.commanded_running = True
        self.commanded_reverse = True
        self.state = VFDState.STARTING

    def stop(self):
        self.driver.stop()

        self.commanded_running = False
        self.stop_samples = 0
        self.state = VFDState.STOPPING

    def update_status(self, status):
        self.actual_frequency_hz = status["frequency_hz"]
        self.actual_rpm = status["rpm"]

        if self.state == VFDState.STOPPING:

            if (
                abs(self.actual_frequency_hz)
                <= self.STOP_FREQUENCY_THRESHOLD
            ):
                self.stop_samples += 1
            else:
                self.stop_samples = 0

            if self.stop_samples >= self.STOP_CONFIRM_SAMPLES:
                self.state = VFDState.IDLE
                self.stop_samples = 0

        elif self.commanded_running:

            if self.actual_frequency_hz > 0.5:
                self.state = VFDState.RUNNING
            else:
                self.state = VFDState.STARTING

