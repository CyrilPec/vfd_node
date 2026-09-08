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
