"""
huanyang_vfd.py

Huanyang HY-series VFD driver.

Target:
    HY01D523B 1.5 kW

Protocol:
    Huanyang RS485 RTU protocol.

This driver is designed to plug into:

    VFDManager
        |
        +-- HuanyangVFD
                |
                +-- Modbus/RS485 transport

IMPORTANT:
    The HY-series communication protocol is not perfectly identical
    between all firmware revisions.

Therefore:
    - protocol framing is implemented here
    - CRC is implemented here
    - command structure is implemented here
    - register/profile values remain configurable

Do NOT operate a spindle at an unknown frequency or voltage.
Verify motor/VFD parameters against the actual nameplates/manual.
"""


from __future__ import annotations

import struct
import time

from dataclasses import dataclass
from typing import Optional, Protocol

try:
    from .vfd_manager import (
        VFDDriver,
        VFDStatus,
        VFDState,
        VFDDirection,
    )
except ImportError:
    from vfd_manager import (
        VFDDriver,
        VFDStatus,
        VFDState,
        VFDDirection,
    )


# =============================================================================
# RS485 TRANSPORT
# =============================================================================


class SerialTransport(Protocol):
    """
    Minimal serial interface required by HuanyangVFD.

    A real implementation can use pyserial.

    Required methods:

        open()
        close()
        write()
        read()
        reset_input_buffer()
    """

    def open(self) -> None:
        ...

    def close(self) -> None:
        ...

    def write(
        self,
        data: bytes,
    ) -> int:
        ...

    def read(
        self,
        size: int,
    ) -> bytes:
        ...

    def reset_input_buffer(self) -> None:
        ...


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class HuanyangConfig:
    """
    Communication configuration.

    Defaults match the commonly documented HY setup:

        Address = 1
        Baud     = 9600
        RTU      = 8N1
    """

    slave_id: int = 1

    baudrate: int = 9600

    timeout: float = 0.2

    inter_frame_delay: float = 0.005

    # Serial format
    bytesize: int = 8

    parity: str = "N"

    stopbits: int = 1


# =============================================================================
# REGISTER MAP
# =============================================================================


@dataclass
class HuanyangRegisterMap:
    """
    Huanyang logical register map.

    The HY protocol has two important groups:

        Function data
        Control data

    The addresses below are intentionally configurable.

    Parameter numbers are represented separately because Huanyang
    parameter access is not the same thing as the normal control-data
    channel.
    """

    # -------------------------------------------------------------------------
    # PARAMETER NUMBERS
    # -------------------------------------------------------------------------

    parameter_run_source: int = 1

    parameter_frequency_source: int = 2

    parameter_main_frequency: int = 3

    parameter_base_frequency: int = 4

    parameter_max_frequency: int = 5

    parameter_min_frequency: int = 11

    parameter_motor_voltage: int = 141

    parameter_motor_current: int = 142

    parameter_motor_poles: int = 143

    parameter_motor_rpm: int = 144

    parameter_address: int = 163

    parameter_baudrate: int = 164

    parameter_data_method: int = 165

    # -------------------------------------------------------------------------
    # CONTROL DATA
    # -------------------------------------------------------------------------

    # These are Huanyang control-data indexes.
    #
    # Common implementations use:
    #
    #     0 = target frequency
    #     1 = output frequency
    #     2 = output current
    #     3 = RPM
    #     4 = DC voltage
    #     5 = AC voltage
    #     6 = status/control
    #     7 = temperature
    #
    # The actual command byte is handled separately.

    target_frequency_index: int = 0

    output_frequency_index: int = 1

    output_current_index: int = 2

    output_rpm_index: int = 3

    dc_voltage_index: int = 4

    ac_voltage_index: int = 5

    status_index: int = 6

    temperature_index: int = 7


# =============================================================================
# CONTROL COMMANDS
# =============================================================================


@dataclass
class HuanyangCommands:
    """
    Huanyang control command values.

    These are kept configurable because firmware variants exist.
    """

    forward: int = 0x01

    reverse: int = 0x02

    stop: int = 0x08

    emergency_stop: int = 0x07

    reset: int = 0x05


# =============================================================================
# CRC16
# =============================================================================


def crc16_modbus(
    data: bytes,
) -> int:
    """
    Calculate CRC16 used by RTU frames.

    Polynomial:
        0xA001

    Initial:
        0xFFFF

    Returned integer:
        low byte + high byte are appended to the frame.
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

    return crc & 0xFFFF


def append_crc(
    data: bytes,
) -> bytes:
    """
    Append Modbus RTU CRC.

    CRC is transmitted:
        low byte
        high byte
    """

    crc = crc16_modbus(
        data
    )

    return data + bytes(
        (
            crc & 0xFF,
            (crc >> 8) & 0xFF,
        )
    )


def check_crc(
    frame: bytes,
) -> bool:
    """
    Validate RTU CRC.
    """

    if len(frame) < 3:
        return False

    payload = frame[:-2]

    received_crc = (
        frame[-2]
        | (frame[-1] << 8)
    )

    calculated_crc = crc16_modbus(
        payload
    )

    return (
        received_crc
        == calculated_crc
    )


# =============================================================================
# HUANYANG DRIVER
# =============================================================================


class HuanyangVFD(VFDDriver):
    """
    Huanyang HY-series VFD driver.

    Intended for HY01D523B and closely related HY-series drives.
    """

    name = "Huanyang HY"

    def __init__(
        self,
        transport: SerialTransport,
        config: Optional[HuanyangConfig] = None,
        registers: Optional[HuanyangRegisterMap] = None,
        commands: Optional[HuanyangCommands] = None,
    ):

        self.transport = transport

        self.config = (
            config
            or HuanyangConfig()
        )

        self.registers = (
            registers
            or HuanyangRegisterMap()
        )

        self.commands = (
            commands
            or HuanyangCommands()
        )

        self.connected = False

        self.last_error = ""

        self.last_status = VFDStatus(
            connected=False,
            state=VFDState.DISCONNECTED,
        )

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def connect(self) -> bool:
        """
        Open RS485 transport.
        """

        try:

            self.transport.open()

            self.connected = True

            self.last_status.connected = True

            self.last_status.state = (
                VFDState.READY
            )

            return True

        except Exception as exc:

            self._error(
                exc
            )

            return False

    def disconnect(self) -> None:
        """
        Close RS485 transport.
        """

        try:

            self.transport.close()

        except Exception:
            pass

        self.connected = False

        self.last_status.connected = False

        self.last_status.running = False

        self.last_status.state = (
            VFDState.DISCONNECTED
        )

    def is_connected(self) -> bool:

        return self.connected

    # =========================================================================
    # START
    # =========================================================================

    def start(self) -> bool:
        """
        Start spindle forward.
        """

        return self.write_control_data(
            self.commands.forward
        )

    # =========================================================================
    # STOP
    # =========================================================================

    def stop(self) -> bool:
        """
        Stop spindle.
        """

        return self.write_control_data(
            self.commands.stop
        )

    # =========================================================================
    # EMERGENCY STOP
    # =========================================================================

    def emergency_stop(self) -> bool:
        """
        Emergency stop.

        Uses the configured Huanyang command value.
        """

        return self.write_control_data(
            self.commands.emergency_stop
        )

    # =========================================================================
    # RESET
    # =========================================================================

    def reset_fault(self) -> bool:
        """
        Reset VFD fault.
        """

        return self.write_control_data(
            self.commands.reset
        )

    # =========================================================================
    # DIRECTION
    # =========================================================================

    def set_direction(
        self,
        direction: VFDDirection,
    ) -> bool:
        """
        Set spindle direction.

        The direction command is sent as a control-data command.
        """

        if direction == (
            VFDDirection.REVERSE
        ):

            command = (
                self.commands.reverse
            )

        else:

            command = (
                self.commands.forward
            )

        return self.write_control_data(
            command
        )

    # =========================================================================
    # FREQUENCY
    # =========================================================================

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        """
        Set spindle frequency.

        Huanyang frequency values are commonly represented in 0.01 Hz units.

        Example:

            400.00 Hz -> 40000
            200.00 Hz -> 20000
        """

        frequency_hz = float(
            frequency_hz
        )

        raw_frequency = int(
            round(
                frequency_hz * 100.0
            )
        )

        return self.write_control_data(
            raw_frequency,
            data_index=(
                self.registers.target_frequency_index
            ),
        )

    # =========================================================================
    # SPEED
    # =========================================================================

    def set_speed(
        self,
        rpm: float,
    ) -> bool:
        """
        Set spindle RPM.

        The HY drive normally uses frequency as the primary speed command.

        Therefore RPM is converted to frequency using the configured
        motor characteristics in VFDManager.

        This method is provided for API completeness.

        If direct RPM control is required, the profile can be extended.
        """

        self.last_error = (
            "Huanyang uses frequency control; "
            "RPM should be converted to frequency "
            "by VFDManager."
        )

        return False

    # =========================================================================
    # CONTROL DATA WRITE
    # =========================================================================

    def write_control_data(
        self,
        value: int,
        data_index: Optional[int] = None,
    ) -> bool:
        """
        Write Huanyang control data.

        This method supports the two common Huanyang forms:

        Command:

            slave
            03
            command
            CRC

        Indexed data:

            slave
            03
            index
            value
            CRC

        The exact interpretation is firmware dependent, so the
        frame construction is kept in this driver.
        """

        if not self.is_connected():

            self.last_error = (
                "VFD is not connected."
            )

            return False

        try:

            slave = (
                self.config.slave_id
            )

            if data_index is None:

                frame = bytes(
                    (
                        slave,
                        0x03,
                        int(value) & 0xFF,
                    )
                )

            else:

                frame = bytes(
                    (
                        slave,
                        0x03,
                        int(data_index) & 0xFF,
                        (int(value) >> 8) & 0xFF,
                        int(value) & 0xFF,
                    )
                )

            frame = append_crc(
                frame
            )

            response = self._transaction(
                frame,
                expected_minimum=4,
            )

            return self._validate_response(
                response
            )

        except Exception as exc:

            self._error(
                exc
            )

            return False

    # =========================================================================
    # FUNCTION DATA READ
    # =========================================================================

    def read_function_data(
        self,
        parameter: int,
    ) -> Optional[int]:
        """
        Read a Huanyang parameter such as PD001, PD002, PD163, etc.

        The documented HY function-data read frame is:

            slave
            01
            length
            parameter
            CRC
        """

        if not self.is_connected():

            self.last_error = (
                "VFD is not connected."
            )

            return None

        parameter = int(
            parameter
        )

        try:

            slave = (
                self.config.slave_id
            )

            frame = bytes(
                (
                    slave,
                    0x01,
                    0x03,
                    (parameter >> 8) & 0xFF,
                    parameter & 0xFF,
                )
            )

            frame = append_crc(
                frame
            )

            response = self._transaction(
                frame,
                expected_minimum=5,
            )

            if not self._validate_response(
                response
            ):

                return None

            return self._parse_function_read(
                response
            )

        except Exception as exc:

            self._error(
                exc
            )

            return None

    # =========================================================================
    # FUNCTION DATA WRITE
    # =========================================================================

    def write_function_data(
        self,
        parameter: int,
        value: int,
    ) -> bool:
        """
        Write a Huanyang parameter.

        Example:

            write_function_data(163, 1)

        corresponds logically to:

            PD163 = 1
        """

        if not self.is_connected():

            self.last_error = (
                "VFD is not connected."
            )

            return False

        parameter = int(
            parameter
        )

        value = int(
            value
        )

        try:

            slave = (
                self.config.slave_id
            )

            frame = bytes(
                (
                    slave,
                    0x02,
                    0x03,
                    (parameter >> 8) & 0xFF,
                    parameter & 0xFF,
                    (value >> 8) & 0xFF,
                    value & 0xFF,
                )
            )

            frame = append_crc(
                frame
            )

            response = self._transaction(
                frame,
                expected_minimum=4,
            )

            return self._validate_response(
                response
            )

        except Exception as exc:

            self._error(
                exc
            )

            return False

    # =========================================================================
    # STATUS / CONTROL DATA READ
    # =========================================================================

    def read_control_data(
        self,
        data_index: int,
    ) -> Optional[int]:
        """
        Read Huanyang control/monitoring data.

        Common indexes:

            0 = target frequency
            1 = output frequency
            2 = output current
            3 = RPM
            4 = DC voltage
            5 = AC voltage
            6 = status/control
            7 = temperature
        """

        if not self.is_connected():

            self.last_error = (
                "VFD is not connected."
            )

            return None

        data_index = int(
            data_index
        )

        try:

            slave = (
                self.config.slave_id
            )

            frame = bytes(
                (
                    slave,
                    0x04,
                    data_index & 0xFF,
                )
            )

            frame = append_crc(
                frame
            )

            response = self._transaction(
                frame,
                expected_minimum=5,
            )

            if not self._validate_response(
                response
            ):

                return None

            return self._parse_control_read(
                response
            )

        except Exception as exc:

            self._error(
                exc
            )

            return None

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> VFDStatus:
        """
        Read current spindle status.

        The HY control-data indexes provide:

            output frequency
            current
            RPM
            DC voltage
            AC voltage

        Status-word interpretation varies by firmware, therefore
        the raw status word is retained.
        """

        status = VFDStatus()

        status.connected = (
            self.is_connected()
        )

        if not status.connected:

            status.state = (
                VFDState.DISCONNECTED
            )

            self.last_status = status

            return status

        try:

            # -----------------------------------------------------------------
            # OUTPUT FREQUENCY
            # -----------------------------------------------------------------

            value = self.read_control_data(
                self.registers.output_frequency_index
            )

            if value is not None:

                status.frequency_hz = (
                    float(value)
                    / 100.0
                )

            # -----------------------------------------------------------------
            # CURRENT
            # -----------------------------------------------------------------

            value = self.read_control_data(
                self.registers.output_current_index
            )

            if value is not None:

                status.current_a = (
                    float(value)
                    / 10.0
                )

            # -----------------------------------------------------------------
            # RPM
            # -----------------------------------------------------------------

            value = self.read_control_data(
                self.registers.output_rpm_index
            )

            if value is not None:

                status.rpm = float(
                    value
                )

            # -----------------------------------------------------------------
            # DC VOLTAGE
            # -----------------------------------------------------------------

            value = self.read_control_data(
                self.registers.dc_voltage_index
            )

            if value is not None:

                status.dc_voltage_v = float(
                    value
                )

            # -----------------------------------------------------------------
            # AC VOLTAGE
            # -----------------------------------------------------------------

            value = self.read_control_data(
                self.registers.ac_voltage_index
            )

            if value is not None:

                status.voltage_v = float(
                    value
                )

            # -----------------------------------------------------------------
            # STATUS WORD
            # -----------------------------------------------------------------

            status_word = self.read_control_data(
                self.registers.status_index
            )

            if status_word is not None:

                status.raw[
                    "status_word"
                ] = status_word

                status.running = (
                    status.frequency_hz > 0.01
                )

            # -----------------------------------------------------------------
            # STATE
            # -----------------------------------------------------------------

            if status.fault:

                status.state = (
                    VFDState.FAULT
                )

            elif status.running:

                status.state = (
                    VFDState.RUNNING
                )

            else:

                status.state = (
                    VFDState.READY
                )

            self.last_status = status

            return status

        except Exception as exc:

            self._error(
                exc
            )

            status.connected = False

            status.state = (
                VFDState.DISCONNECTED
            )

            self.last_status = status

            return status

    # =========================================================================
    # CONFIGURATION HELPERS
    # =========================================================================

    def configure_communication(
        self,
        *,
        address: Optional[int] = None,
        baudrate: Optional[int] = None,
    ) -> bool:
        """
        Change communication settings in the VFD.

        NOTE:
            Changing the VFD baud/address can immediately make the
            current connection unusable. Reconnect afterward.
        """

        success = True

        if address is not None:

            success = (
                self.write_function_data(
                    self.registers.parameter_address,
                    int(address),
                )
                and success
            )

        if baudrate is not None:

            code = self.baudrate_to_parameter(
                baudrate
            )

            if code is None:

                self.last_error = (
                    f"Unsupported baud rate: "
                    f"{baudrate}"
                )

                success = False

            else:

                success = (
                    self.write_function_data(
                        self.registers.parameter_baudrate,
                        code,
                    )
                    and success
                )

        return success

    @staticmethod
    def baudrate_to_parameter(
        baudrate: int,
    ) -> Optional[int]:
        """
        Convert baud rate into Huanyang PD164 value.

        Common documented mapping:

            0 = 4800
            1 = 9600
            2 = 19200
            3 = 38400
        """

        mapping = {
            4800: 0,
            9600: 1,
            19200: 2,
            38400: 3,
        }

        return mapping.get(
            int(baudrate)
        )

    # =========================================================================
    # TRANSACTION
    # =========================================================================

    def _transaction(
        self,
        frame: bytes,
        expected_minimum: int = 4,
    ) -> bytes:
        """
        Send one RS485 frame and read the response.

        The transport implementation determines how much data is physically
        received. This layer performs protocol validation.
        """

        if not self.is_connected():

            raise ConnectionError(
                "VFD is not connected."
            )

        # ---------------------------------------------------------------------
        # INTER-FRAME DELAY
        # ---------------------------------------------------------------------

        if self.config.inter_frame_delay > 0:

            time.sleep(
                self.config.inter_frame_delay
            )

        # ---------------------------------------------------------------------
        # CLEAR RX
        # ---------------------------------------------------------------------

        reset = getattr(
            self.transport,
            "reset_input_buffer",
            None,
        )

        if callable(reset):

            reset()

        # ---------------------------------------------------------------------
        # WRITE
        # ---------------------------------------------------------------------

        self.transport.write(
            frame
        )

        # ---------------------------------------------------------------------
        # READ
        # ---------------------------------------------------------------------

        response = self._read_response(
            expected_minimum
        )

        return response

    # =========================================================================
    # RESPONSE READ
    # =========================================================================

    def _read_response(
        self,
        expected_minimum: int,
    ) -> bytes:
        """
        Read an RTU response.

        Because different Huanyang operations produce different frame sizes,
        this method starts with the minimum frame and then reads additional
        bytes when the response advertises a byte count.
        """

        deadline = (
            time.monotonic()
            + self.config.timeout
        )

        buffer = bytearray()

        # ---------------------------------------------------------------------
        # READ FIRST BYTES
        # ---------------------------------------------------------------------

        while (
            len(buffer) < expected_minimum
            and time.monotonic() < deadline
        ):

            chunk = self.transport.read(
                expected_minimum
                - len(buffer)
            )

            if chunk:

                buffer.extend(
                    chunk
                )

            else:

                time.sleep(
                    0.001
                )

        if len(buffer) < expected_minimum:

            raise TimeoutError(
                "Timeout waiting for Huanyang response."
            )

        # ---------------------------------------------------------------------
        # DETERMINE EXPECTED LENGTH
        # ---------------------------------------------------------------------

        expected_length = self._response_length(
            bytes(buffer)
        )

        if expected_length is None:

            # If the protocol cannot determine the exact size,
            # return what we already have.
            return bytes(buffer)

        # ---------------------------------------------------------------------
        # READ REMAINDER
        # ---------------------------------------------------------------------

        while (
            len(buffer) < expected_length
            and time.monotonic() < deadline
        ):

            chunk = self.transport.read(
                expected_length
                - len(buffer)
            )

            if chunk:

                buffer.extend(
                    chunk
                )

            else:

                time.sleep(
                    0.001
                )

        if len(buffer) < expected_length:

            raise TimeoutError(
                "Incomplete Huanyang response."
            )

        return bytes(
            buffer[:expected_length]
        )

    # =========================================================================
    # RESPONSE LENGTH
    # =========================================================================

    @staticmethod
    def _response_length(
        frame: bytes,
    ) -> Optional[int]:
        """
        Determine expected response length.

        Common RTU forms:

            address + function + byte_count + data + CRC

        For normal fixed command acknowledgements, the response is usually
        8 bytes or similar depending on the command.
        """

        if len(frame) < 3:

            return None

        function = frame[1]

        # ---------------------------------------------------------------------
        # EXCEPTION
        # ---------------------------------------------------------------------

        if function & 0x80:

            return 5

        # ---------------------------------------------------------------------
        # BYTE COUNT FORM
        # ---------------------------------------------------------------------

        byte_count = frame[2]

        if byte_count <= 32:

            return (
                3
                + byte_count
                + 2
            )

        return None

    # =========================================================================
    # PARSERS
    # =========================================================================

    @staticmethod
    def _parse_function_read(
        response: bytes,
    ) -> Optional[int]:
        """
        Parse function-data read response.

        Common response:

            slave
            function
            byte_count
            data...
            CRC
        """

        if len(response) < 5:

            return None

        byte_count = response[2]

        if byte_count <= 0:

            return None

        data_start = 3

        data_end = (
            data_start
            + byte_count
        )

        if data_end > len(response) - 2:

            return None

        data = response[
            data_start:data_end
        ]

        if len(data) == 1:

            return data[0]

        if len(data) >= 2:

            return int.from_bytes(
                data[:2],
                byteorder="big",
                signed=False,
            )

        return None

    @staticmethod
    def _parse_control_read(
        response: bytes,
    ) -> Optional[int]:
        """
        Parse control-data read response.

        Usually a 16-bit value.
        """

        if len(response) < 5:

            return None

        byte_count = response[2]

        if byte_count < 2:

            return None

        if len(response) < 5:

            return None

        return int.from_bytes(
            response[3:5],
            byteorder="big",
            signed=False,
        )

    # =========================================================================
    # RESPONSE VALIDATION
    # =========================================================================

    def _validate_response(
        self,
        response: bytes,
    ) -> bool:
        """
        Validate slave address and CRC.
        """

        if not response:

            self.last_error = (
                "Empty response."
            )

            return False

        if not check_crc(
            response
        ):

            self.last_error = (
                "Invalid CRC."
            )

            return False

        if response[0] != (
            self.config.slave_id
        ):

            self.last_error = (
                "Unexpected slave address."
            )

            return False

        # ---------------------------------------------------------------------
        # MODBUS/HUANYANG EXCEPTION
        # ---------------------------------------------------------------------

        if len(response) > 1:

            if response[1] & 0x80:

                self.last_error = (
                    f"VFD exception response: "
                    f"0x{response[2]:02X}"
                    if len(response) > 2
                    else "VFD exception response."
                )

                return False

        return True

    # =========================================================================
    # ERROR
    # =========================================================================

    def _error(
        self,
        error: Exception | str,
    ) -> None:

        self.last_error = str(
            error
        )

        self.last_status.connected = False

        self.last_status.state = (
            VFDState.DISCONNECTED
        )


# =============================================================================
# PYTHON SERIAL TRANSPORT
# =============================================================================


class PySerialTransport:
    """
    Optional pyserial transport.

    This keeps pyserial out of the protocol code.

    Usage:

        transport = PySerialTransport(
            port="COM5",
            baudrate=9600,
        )

        vfd = HuanyangVFD(
            transport
        )
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 0.2,
    ):

        self.port = port

        self.baudrate = int(
            baudrate
        )

        self.timeout = float(
            timeout
        )

        self.serial = None

    def open(self) -> None:

        try:

            import serial

        except ImportError as exc:

            raise ImportError(
                "pyserial is required for "
                "PySerialTransport."
            ) from exc

        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )

    def close(self) -> None:

        if self.serial is not None:

            self.serial.close()

            self.serial = None

    def write(
        self,
        data: bytes,
    ) -> int:

        if self.serial is None:

            raise ConnectionError(
                "Serial port is not open."
            )

        return self.serial.write(
            data
        )

    def read(
        self,
        size: int,
    ) -> bytes:

        if self.serial is None:

            raise ConnectionError(
                "Serial port is not open."
            )

        return self.serial.read(
            size
        )

    def reset_input_buffer(self) -> None:

        if self.serial is not None:

            self.serial.reset_input_buffer()


# =============================================================================
# TEST / DIAGNOSTIC TRANSPORT
# =============================================================================


class LoopbackTransport:
    """
    Simple test transport.

    It does not communicate with a VFD.

    Useful for testing CRC/frame generation.
    """

    def __init__(self):

        self.last_frame = b""

        self.response = b""

        self.opened = False

    def open(self) -> None:

        self.opened = True

    def close(self) -> None:

        self.opened = False

    def write(
        self,
        data: bytes,
    ) -> int:

        self.last_frame = bytes(
            data
        )

        return len(data)

    def read(
        self,
        size: int,
    ) -> bytes:

        data = self.response[
            :size
        ]

        self.response = (
            self.response[size:]
        )

        return data

    def reset_input_buffer(self) -> None:

        self.response = b""


# =============================================================================
# BUILD EXAMPLE
# =============================================================================


def create_hy01d523b_driver(
    transport: SerialTransport,
    slave_id: int = 1,
) -> HuanyangVFD:
    """
    Create a driver configured for the typical HY01D523B setup.

    Communication:

        slave     = 1
        baudrate  = 9600
        8N1
        RTU

    The VFD itself should be configured accordingly.
    """

    config = HuanyangConfig(
        slave_id=slave_id,
        baudrate=9600,
        timeout=0.2,
        bytesize=8,
        parity="N",
        stopbits=1,
    )

    return HuanyangVFD(
        transport=transport,
        config=config,
        registers=HuanyangRegisterMap(),
        commands=HuanyangCommands(),
    )


# =============================================================================
# EXAMPLE
# =============================================================================


if __name__ == "__main__":

    print(
        "Huanyang HY VFD driver test"
    )

    # -------------------------------------------------------------------------
    # CRC TEST
    # -------------------------------------------------------------------------

    test_frame = bytes(
        (
            0x01,
            0x01,
            0x03,
            0x00,
            0x01,
        )
    )

    frame_with_crc = append_crc(
        test_frame
    )

    print(
        "Frame:",
        frame_with_crc.hex(
            " "
        ),
    )

    print(
        "CRC valid:",
        check_crc(
            frame_with_crc
        ),
    )

    # -------------------------------------------------------------------------
    # DRIVER TEST
    # -------------------------------------------------------------------------

    transport = LoopbackTransport()

    vfd = create_hy01d523b_driver(
        transport,
        slave_id=1,
    )

    print(
        "Connect:",
        vfd.connect(),
    )

    # -------------------------------------------------------------------------
    # FRAME TEST
    # -------------------------------------------------------------------------

    # Do NOT send to a real VFD here.
    #
    # This simply demonstrates the command construction.

    vfd.write_control_data(
        0x01
    )

    print(
        "Generated frame:",
        transport.last_frame.hex(
            " "
        ),
    )

    vfd.disconnect()

    print(
        "Done."
    )
