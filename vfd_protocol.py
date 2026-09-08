from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


class VFDProtocolError(Exception):
    """Base protocol error."""


class VFDTimeoutError(VFDProtocolError):
    """VFD did not respond in time."""


class VFDCRCError(VFDProtocolError):
    """VFD response contained an invalid CRC."""


class VFDResponseError(VFDProtocolError):
    """VFD response was malformed or unexpected."""


class CommunicationState(Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    CRC_ERROR = "crc_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass
class CommunicationStats:
    tx_count: int = 0
    rx_count: int = 0
    timeout_count: int = 0
    crc_error_count: int = 0
    invalid_response_count: int = 0
    consecutive_failures: int = 0


def crc16_modbus(data: bytes) -> int:
    """
    Modbus RTU CRC16.

    Returned as an integer. When transmitted, the low byte
    is sent first, followed by the high byte.
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc & 0xFFFF


def append_crc(data: bytes) -> bytes:
    crc = crc16_modbus(data)
    return data + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> bool:
    if len(frame) < 3:
        return False

    received_crc = frame[-2] | (frame[-1] << 8)
    calculated_crc = crc16_modbus(frame[:-2])

    return received_crc == calculated_crc


class VFDProtocol:
    """
    Generic RS485/Modbus-like transaction layer.

    `transport` must provide:

        write(data: bytes)
        read(timeout: float) -> bytes
        reset_input_buffer()
    """

    def __init__(
        self,
        transport,
        slave_id: int = 4,
        timeout: float = 0.25,
        retries: int = 2,
    ):
        self.transport = transport
        self.slave_id = slave_id
        self.timeout = timeout
        self.retries = retries

        self.stats = CommunicationStats()
        self.communication_state = CommunicationState.OK

    def build_frame(self, payload: bytes) -> bytes:
        return append_crc(payload)

    def validate_frame(self, frame: bytes) -> None:
        if len(frame) < 3:
            raise VFDResponseError("Response too short")

        if frame[0] != self.slave_id:
            raise VFDResponseError(
                f"Unexpected slave ID: {frame[0]}"
            )

        if not verify_crc(frame):
            raise VFDCRCError("Invalid CRC")

    def transaction(self, payload: bytes) -> bytes:
        frame = self.build_frame(payload)

        last_error = None

        for _ in range(self.retries + 1):
            try:
                self.stats.tx_count += 1

                self.transport.reset_input_buffer()
                self.transport.write(frame)

                response = self.transport.read(self.timeout)

                if not response:
                    raise VFDTimeoutError("No response from VFD")

                self.validate_frame(response)

                self.stats.rx_count += 1
                self.stats.consecutive_failures = 0
                self.communication_state = CommunicationState.OK

                return response

            except VFDTimeoutError as exc:
                self.stats.timeout_count += 1
                last_error = exc
                self.communication_state = CommunicationState.TIMEOUT

            except VFDCRCError as exc:
                self.stats.crc_error_count += 1
                last_error = exc
                self.communication_state = CommunicationState.CRC_ERROR

            except VFDResponseError as exc:
                self.stats.invalid_response_count += 1
                last_error = exc
                self.communication_state = (
                    CommunicationState.INVALID_RESPONSE
                )

        self.stats.consecutive_failures += 1
        raise last_error
