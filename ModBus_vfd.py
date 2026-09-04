"""
modbus_vfd.py

Generic Modbus VFD driver for Scn6Studio.

This module provides the Modbus transport layer for VFDManager.

IMPORTANT:
    This file does NOT contain registers for a specific VFD brand.

Different VFDs use different:
    - register addresses
    - command values
    - frequency scaling
    - RPM scaling
    - status bits
    - fault registers

Those values belong in a VFD profile.

Architecture:

    SCN6 VFD Node
          |
          v
      VFDManager
          |
          v
      ModbusVFD
          |
          +---- ModbusClient
          |
          v
      VFDProfile
          |
          v
        VFD


The transport is intentionally separated from the register map.

Later we can add profiles such as:

    HuanyangProfile
    FulingProfile
    DeltaProfile
    INVTProfile
    GenericModbusProfile
"""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

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
# MODBUS TRANSPORT INTERFACE
# =============================================================================


class ModbusClientProtocol(Protocol):
    """
    Minimal interface required by ModbusVFD.

    A real implementation can use:
        - pymodbus
        - a custom serial Modbus implementation
        - Modbus TCP
        - another transport

    ModbusVFD does not depend on a specific library.
    """

    def connect(self) -> bool:
        ...

    def close(self) -> None:
        ...

    def is_connected(self) -> bool:
        ...

    def read_holding_registers(
        self,
        address: int,
        count: int,
        slave: int,
    ) -> list[int]:
        ...

    def read_input_registers(
        self,
        address: int,
        count: int,
        slave: int,
    ) -> list[int]:
        ...

    def write_register(
        self,
        address: int,
        value: int,
        slave: int,
    ) -> bool:
        ...

    def write_registers(
        self,
        address: int,
        values: list[int],
        slave: int,
    ) -> bool:
        ...


# =============================================================================
# REGISTER TYPES
# =============================================================================


class RegisterType:
    """
    Modbus register types.
    """

    HOLDING = "holding"

    INPUT = "input"


# =============================================================================
# REGISTER DESCRIPTION
# =============================================================================


@dataclass
class ModbusRegister:
    """
    Description of one VFD register.
    """

    address: int

    register_type: str = RegisterType.HOLDING

    count: int = 1

    scale: float = 1.0

    offset: float = 0.0

    signed: bool = False

    writable: bool = False

    readable: bool = True

    min_value: Optional[float] = None

    max_value: Optional[float] = None

    description: str = ""


# =============================================================================
# VFD MODBUS PROFILE
# =============================================================================


@dataclass
class ModbusVFDProfile:
    """
    Generic VFD Modbus register profile.

    A VFD manufacturer/model can provide its own profile.

    Example:

        profile = ModbusVFDProfile(
            name="My VFD",
            frequency_write=ModbusRegister(
                address=0x2001,
                scale=100.0,
                writable=True,
            ),
        )

    No manufacturer-specific values are included here.
    """

    name: str = "Generic Modbus VFD"

    # -------------------------------------------------------------------------
    # COMMAND REGISTERS
    # -------------------------------------------------------------------------

    command_register: Optional[ModbusRegister] = None

    frequency_write: Optional[ModbusRegister] = None

    speed_write: Optional[ModbusRegister] = None

    direction_register: Optional[ModbusRegister] = None

    reset_register: Optional[ModbusRegister] = None

    # -------------------------------------------------------------------------
    # STATUS REGISTERS
    # -------------------------------------------------------------------------

    status_register: Optional[ModbusRegister] = None

    frequency_read: Optional[ModbusRegister] = None

    speed_read: Optional[ModbusRegister] = None

    current_read: Optional[ModbusRegister] = None

    voltage_read: Optional[ModbusRegister] = None

    power_read: Optional[ModbusRegister] = None

    dc_voltage_read: Optional[ModbusRegister] = None

    fault_read: Optional[ModbusRegister] = None

    warning_read: Optional[ModbusRegister] = None

    # -------------------------------------------------------------------------
    # COMMAND VALUES
    # -------------------------------------------------------------------------

    start_value: Optional[int] = None

    stop_value: Optional[int] = None

    emergency_stop_value: Optional[int] = None

    forward_value: Optional[int] = None

    reverse_value: Optional[int] = None

    reset_value: Optional[int] = None

    # -------------------------------------------------------------------------
    # STATUS BIT DEFINITIONS
    # -------------------------------------------------------------------------

    running_bit: Optional[int] = None

    fault_bit: Optional[int] = None

    warning_bit: Optional[int] = None

    reverse_bit: Optional[int] = None

    # -------------------------------------------------------------------------
    # OPTIONAL FAULT TABLE
    # -------------------------------------------------------------------------

    fault_codes: dict[int, str] = field(
        default_factory=dict
    )


# =============================================================================
# DEFAULT PROFILE
# =============================================================================


def create_generic_profile() -> ModbusVFDProfile:
    """
    Create an empty generic Modbus profile.

    No register addresses are assumed.
    """

    return ModbusVFDProfile()


# =============================================================================
# MODBUS VFD DRIVER
# =============================================================================


class ModbusVFD(VFDDriver):
    """
    Generic Modbus VFD driver.

    This class translates universal VFD commands into Modbus operations
    using a supplied ModbusVFDProfile.
    """

    name = "Generic Modbus VFD"

    def __init__(
        self,
        client: ModbusClientProtocol,
        profile: Optional[ModbusVFDProfile] = None,
        slave_id: int = 1,
    ):

        self.client = client

        self.profile = (
            profile
            or create_generic_profile()
        )

        self.slave_id = int(slave_id)

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
        Connect to the Modbus transport.
        """

        try:

            result = self.client.connect()

            self.connected = bool(result)

            if self.connected:

                self.last_status.connected = True

                self.last_status.state = (
                    VFDState.READY
                )

            return self.connected

        except Exception as exc:

            self._set_error(exc)

            return False

    def disconnect(self) -> None:
        """
        Disconnect Modbus transport.
        """

        try:

            self.client.close()

        except Exception:
            pass

        self.connected = False

        self.last_status.connected = False

        self.last_status.running = False

        self.last_status.state = (
            VFDState.DISCONNECTED
        )

    def is_connected(self) -> bool:
        """
        Return transport connection state.
        """

        if not self.connected:
            return False

        try:

            return bool(
                self.client.is_connected()
            )

        except Exception:

            return self.connected

    # =========================================================================
    # START
    # =========================================================================

    def start(self) -> bool:
        """
        Start VFD.
        """

        register = (
            self.profile.command_register
        )

        value = (
            self.profile.start_value
        )

        if register is None:
            return self._unsupported(
                "Start command register is not configured."
            )

        if value is None:
            return self._unsupported(
                "Start command value is not configured."
            )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # STOP
    # =========================================================================

    def stop(self) -> bool:
        """
        Stop VFD.
        """

        register = (
            self.profile.command_register
        )

        value = (
            self.profile.stop_value
        )

        if register is None:
            return self._unsupported(
                "Stop command register is not configured."
            )

        if value is None:
            return self._unsupported(
                "Stop command value is not configured."
            )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # EMERGENCY STOP
    # =========================================================================

    def emergency_stop(self) -> bool:
        """
        Emergency stop.

        The actual Modbus command is profile dependent.
        """

        register = (
            self.profile.command_register
        )

        value = (
            self.profile.emergency_stop_value
        )

        if register is None:
            return self._unsupported(
                "Emergency-stop register is not configured."
            )

        if value is None:
            return self._unsupported(
                "Emergency-stop value is not configured."
            )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # RESET FAULT
    # =========================================================================

    def reset_fault(self) -> bool:
        """
        Reset VFD fault.
        """

        register = (
            self.profile.reset_register
        )

        value = (
            self.profile.reset_value
        )

        if register is None:
            return self._unsupported(
                "Reset register is not configured."
            )

        if value is None:
            return self._unsupported(
                "Reset value is not configured."
            )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # FREQUENCY
    # =========================================================================

    def set_frequency(
        self,
        frequency_hz: float,
    ) -> bool:
        """
        Write target frequency.
        """

        register = (
            self.profile.frequency_write
        )

        if register is None:
            return self._unsupported(
                "Frequency register is not configured."
            )

        value = self._encode_value(
            register,
            frequency_hz,
        )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # SPEED
    # =========================================================================

    def set_speed(
        self,
        rpm: float,
    ) -> bool:
        """
        Write target RPM if the VFD profile supports a dedicated RPM register.

        Many VFDs use frequency as the actual command, so a profile may leave
        speed_write unset.
        """

        register = (
            self.profile.speed_write
        )

        if register is None:

            return self._unsupported(
                "Dedicated RPM register is not configured."
            )

        value = self._encode_value(
            register,
            rpm,
        )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # DIRECTION
    # =========================================================================

    def set_direction(
        self,
        direction: VFDDirection,
    ) -> bool:
        """
        Set forward/reverse direction.
        """

        register = (
            self.profile.direction_register
        )

        if register is None:
            return self._unsupported(
                "Direction register is not configured."
            )

        if direction == VFDDirection.REVERSE:

            value = (
                self.profile.reverse_value
            )

        else:

            value = (
                self.profile.forward_value
            )

        if value is None:
            return self._unsupported(
                "Direction values are not configured."
            )

        return self._write_register(
            register,
            value,
        )

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> VFDStatus:
        """
        Read all configured status registers and normalize them into
        VFDStatus.
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
            # STATUS WORD
            # -----------------------------------------------------------------

            status_word = None

            if self.profile.status_register:

                status_word = self._read_value(
                    self.profile.status_register
                )

                if status_word is not None:

                    status.running = (
                        self._get_bit(
                            int(status_word),
                            self.profile.running_bit,
                        )
                    )

                    status.fault = (
                        self._get_bit(
                            int(status_word),
                            self.profile.fault_bit,
                        )
                    )

                    status.warning = (
                        self._get_bit(
                            int(status_word),
                            self.profile.warning_bit,
                        )
                    )

                    if self._get_bit(
                        int(status_word),
                        self.profile.reverse_bit,
                    ):

                        status.direction = (
                            VFDDirection.REVERSE
                        )

                    else:

                        status.direction = (
                            VFDDirection.FORWARD
                        )

            # -----------------------------------------------------------------
            # FREQUENCY
            # -----------------------------------------------------------------

            if self.profile.frequency_read:

                value = self._read_value(
                    self.profile.frequency_read
                )

                if value is not None:

                    status.frequency_hz = (
                        float(value)
                    )

            # -----------------------------------------------------------------
            # RPM
            # -----------------------------------------------------------------

            if self.profile.speed_read:

                value = self._read_value(
                    self.profile.speed_read
                )

                if value is not None:

                    status.rpm = float(value)

            # -----------------------------------------------------------------
            # CURRENT
            # -----------------------------------------------------------------

            if self.profile.current_read:

                value = self._read_value(
                    self.profile.current_read
                )

                if value is not None:

                    status.current_a = float(value)

            # -----------------------------------------------------------------
            # VOLTAGE
            # -----------------------------------------------------------------

            if self.profile.voltage_read:

                value = self._read_value(
                    self.profile.voltage_read
                )

                if value is not None:

                    status.voltage_v = float(value)

            # -----------------------------------------------------------------
            # POWER
            # -----------------------------------------------------------------

            if self.profile.power_read:

                value = self._read_value(
                    self.profile.power_read
                )

                if value is not None:

                    status.power_kw = float(value)

            # -----------------------------------------------------------------
            # DC VOLTAGE
            # -----------------------------------------------------------------

            if self.profile.dc_voltage_read:

                value = self._read_value(
                    self.profile.dc_voltage_read
                )

                if value is not None:

                    status.dc_voltage_v = float(value)

            # -----------------------------------------------------------------
            # FAULT CODE
            # -----------------------------------------------------------------

            if self.profile.fault_read:

                value = self._read_value(
                    self.profile.fault_read
                )

                if value is not None:

                    status.fault_code = int(
                        value
                    )

                    status.fault = (
                        status.fault
                        or status.fault_code != 0
                    )

                    status.fault_text = (
                        self.profile.fault_codes.get(
                            status.fault_code,
                            "",
                        )
                    )

            # -----------------------------------------------------------------
            # WARNING CODE
            # -----------------------------------------------------------------

            if self.profile.warning_read:

                value = self._read_value(
                    self.profile.warning_read
                )

                if value is not None:

                    status.warning_code = int(
                        value
                    )

                    if status.warning_code:

                        status.warning = True

                    status.warning_text = (
                        self.profile.fault_codes.get(
                            status.warning_code,
                            "",
                        )
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

            # -----------------------------------------------------------------
            # RAW DATA
            # -----------------------------------------------------------------

            if status_word is not None:

                status.raw[
                    "status_word"
                ] = status_word

            self.last_status = status

            return status

        except Exception as exc:

            self._set_error(exc)

            status.connected = False

            status.state = (
                VFDState.DISCONNECTED
            )

            self.last_status = status

            return status

    # =========================================================================
    # RAW MODBUS READ
    # =========================================================================

    def read_register(
        self,
        register: ModbusRegister,
    ) -> list[int]:
        """
        Read raw Modbus register values.

        This is intentionally public so diagnostic tools can inspect
        arbitrary registers later.
        """

        if not self.is_connected():

            raise ConnectionError(
                "Modbus VFD is not connected."
            )

        if register.register_type == (
            RegisterType.INPUT
        ):

            return list(
                self.client.read_input_registers(
                    register.address,
                    register.count,
                    self.slave_id,
                )
            )

        return list(
            self.client.read_holding_registers(
                register.address,
                register.count,
                self.slave_id,
            )
        )

    # =========================================================================
    # RAW MODBUS WRITE
    # =========================================================================

    def write_register(
        self,
        address: int,
        value: int,
    ) -> bool:
        """
        Write a raw holding register.

        Intended for diagnostics and future profile configuration.
        """

        if not self.is_connected():
            return False

        try:

            return bool(
                self.client.write_register(
                    int(address),
                    int(value),
                    self.slave_id,
                )
            )

        except Exception as exc:

            self._set_error(exc)

            return False

    # =========================================================================
    # INTERNAL READ
    # =========================================================================

    def _read_value(
        self,
        register: ModbusRegister,
    ) -> Optional[float]:
        """
        Read and decode a configured register.
        """

        values = self.read_register(
            register
        )

        if not values:
            return None

        raw_value = self._decode_registers(
            values,
            register,
        )

        return (
            raw_value
            * register.scale
            + register.offset
        )

    # =========================================================================
    # INTERNAL WRITE
    # =========================================================================

    def _write_register(
        self,
        register: ModbusRegister,
        value: int,
    ) -> bool:
        """
        Write one configured register.
        """

        if not self.is_connected():
            return False

        if not register.writable:

            self.last_error = (
                "Register is not writable."
            )

            return False

        try:

            return bool(
                self.client.write_register(
                    register.address,
                    int(value),
                    self.slave_id,
                )
            )

        except Exception as exc:

            self._set_error(exc)

            return False

    # =========================================================================
    # ENCODING
    # =========================================================================

    def _encode_value(
        self,
        register: ModbusRegister,
        value: float,
    ) -> int:
        """
        Convert engineering value into raw Modbus value.

        Example:

            scale = 100

            400 Hz -> 40000
        """

        value = float(value)

        if register.min_value is not None:

            value = max(
                value,
                register.min_value,
            )

        if register.max_value is not None:

            value = min(
                value,
                register.max_value,
            )

        if register.scale == 0:

            raise ValueError(
                "Register scale cannot be zero."
            )

        raw = (
            value - register.offset
        ) / register.scale

        raw = int(
            round(raw)
        )

        if register.signed:

            return raw & 0xFFFF

        return max(
            0,
            min(
                raw,
                0xFFFF,
            ),
        )

    # =========================================================================
    # DECODING
    # =========================================================================

    def _decode_registers(
        self,
        values: list[int],
        register: ModbusRegister,
    ) -> int:
        """
        Decode one or multiple 16-bit registers.

        Current implementation supports:

            1 register
            2 registers

        Two-register values are interpreted as big-endian
        32-bit integers.
        """

        if not values:

            return 0

        if register.count <= 1:

            raw = int(values[0]) & 0xFFFF

            if register.signed:

                if raw & 0x8000:

                    raw -= 0x10000

            return raw

        # ---------------------------------------------------------------------
        # 32-BIT
        # ---------------------------------------------------------------------

        raw = 0

        for value in values[:register.count]:

            raw = (
                (raw << 16)
                | (int(value) & 0xFFFF)
            )

        if register.signed:

            bits = (
                16
                * register.count
            )

            sign_bit = (
                1 << (bits - 1)
            )

            if raw & sign_bit:

                raw -= (
                    1 << bits
                )

        return raw

    # =========================================================================
    # STATUS BITS
    # =========================================================================

    @staticmethod
    def _get_bit(
        value: int,
        bit: Optional[int],
    ) -> bool:
        """
        Return a bit from a status word.

        If bit is None, returns False.
        """

        if bit is None:
            return False

        if bit < 0:
            return False

        return bool(
            value
            & (1 << bit)
        )

    # =========================================================================
    # ERRORS
    # =========================================================================

    def _set_error(
        self,
        error: Exception | str,
    ) -> None:
        """
        Store driver error.
        """

        self.last_error = str(
            error
        )

        self.connected = False

        self.last_status.connected = False

        self.last_status.state = (
            VFDState.DISCONNECTED
        )

    def _unsupported(
        self,
        message: str,
    ) -> bool:
        """
        Report an unsupported/unconfigured operation.
        """

        self.last_error = message

        return False


# =============================================================================
# SIMPLE MEMORY MODBUS CLIENT
# =============================================================================


class MemoryModbusClient:
    """
    Small fake Modbus client for development/testing.

    This allows the VFD manager and Modbus driver to be tested without
    connecting real hardware.

    It is NOT a real Modbus implementation.
    """

    def __init__(self):

        self.connected = False

        self.registers: dict[int, int] = {}

    def connect(self) -> bool:

        self.connected = True

        return True

    def close(self) -> None:

        self.connected = False

    def is_connected(self) -> bool:

        return self.connected

    def read_holding_registers(
        self,
        address: int,
        count: int,
        slave: int,
    ) -> list[int]:

        if not self.connected:

            raise ConnectionError(
                "Client is not connected."
            )

        return [
            self.registers.get(
                address + index,
                0,
            )
            for index in range(count)
        ]

    def read_input_registers(
        self,
        address: int,
        count: int,
        slave: int,
    ) -> list[int]:

        return self.read_holding_registers(
            address,
            count,
            slave,
        )

    def write_register(
        self,
        address: int,
        value: int,
        slave: int,
    ) -> bool:

        if not self.connected:

            raise ConnectionError(
                "Client is not connected."
            )

        self.registers[
            int(address)
        ] = int(value)

        return True

    def write_registers(
        self,
        address: int,
        values: list[int],
        slave: int,
    ) -> bool:

        if not self.connected:

            raise ConnectionError(
                "Client is not connected."
            )

        for index, value in enumerate(
            values
        ):

            self.registers[
                address + index
            ] = int(value)

        return True


# =============================================================================
# TEST PROFILE
# =============================================================================


def create_test_profile() -> ModbusVFDProfile:
    """
    Create a completely artificial profile for testing.

    These addresses are NOT for a real VFD.
    """

    return ModbusVFDProfile(

        name="Test VFD",

        # ---------------------------------------------------------------------
        # COMMAND
        # ---------------------------------------------------------------------

        command_register=ModbusRegister(
            address=0,
            writable=True,
        ),

        frequency_write=ModbusRegister(
            address=1,
            scale=0.01,
            writable=True,
        ),

        direction_register=ModbusRegister(
            address=2,
            writable=True,
        ),

        reset_register=ModbusRegister(
            address=3,
            writable=True,
        ),

        # ---------------------------------------------------------------------
        # STATUS
        # ---------------------------------------------------------------------

        status_register=ModbusRegister(
            address=10,
            readable=True,
        ),

        frequency_read=ModbusRegister(
            address=11,
            scale=0.01,
            readable=True,
        ),

        current_read=ModbusRegister(
            address=12,
            scale=0.1,
            readable=True,
        ),

        voltage_read=ModbusRegister(
            address=13,
            scale=1.0,
            readable=True,
        ),

        fault_read=ModbusRegister(
            address=14,
            readable=True,
        ),

        # ---------------------------------------------------------------------
        # COMMAND VALUES
        # ---------------------------------------------------------------------

        start_value=1,

        stop_value=0,

        emergency_stop_value=2,

        forward_value=0,

        reverse_value=1,

        reset_value=1,

        # ---------------------------------------------------------------------
        # STATUS BITS
        # ---------------------------------------------------------------------

        running_bit=0,

        fault_bit=1,

        warning_bit=2,

        reverse_bit=3,
    )


# =============================================================================
# TEST
# =============================================================================


if __name__ == "__main__":

    print(
        "Testing generic Modbus VFD driver..."
    )

    # -------------------------------------------------------------------------
    # FAKE CLIENT
    # -------------------------------------------------------------------------

    client = MemoryModbusClient()

    # -------------------------------------------------------------------------
    # TEST PROFILE
    # -------------------------------------------------------------------------

    profile = create_test_profile()

    # -------------------------------------------------------------------------
    # DRIVER
    # -------------------------------------------------------------------------

    driver = ModbusVFD(
        client=client,
        profile=profile,
        slave_id=1,
    )

    print(
        "Connect:",
        driver.connect(),
    )

    # -------------------------------------------------------------------------
    # COMMANDS
    # -------------------------------------------------------------------------

    print(
        "Set frequency:",
        driver.set_frequency(
            200.0
        ),
    )

    print(
        "Start:",
        driver.start(),
    )

    print(
        "Reverse:",
        driver.set_direction(
            VFDDirection.REVERSE
        ),
    )

    # -------------------------------------------------------------------------
    # SIMULATE VFD STATUS
    # -------------------------------------------------------------------------

    # Running + Reverse
    client.registers[10] = (
        (1 << 0)
        | (1 << 3)
    )

    # 200.00 Hz
    client.registers[11] = 20000

    # 5.0 A
    client.registers[12] = 50

    # 220 V
    client.registers[13] = 220

    # No fault
    client.registers[14] = 0

    # -------------------------------------------------------------------------
    # READ STATUS
    # -------------------------------------------------------------------------

    status = driver.get_status()

    print(
        "Connected:",
        status.connected,
    )

    print(
        "State:",
        status.state.value,
    )

    print(
        "Running:",
        status.running,
    )

    print(
        "Direction:",
        status.direction.value,
    )

    print(
        "Frequency:",
        status.frequency_hz,
        "Hz",
    )

    print(
        "Current:",
        status.current_a,
        "A",
    )

    print(
        "Voltage:",
        status.voltage_v,
        "V",
    )

    print(
        "Fault:",
        status.fault,
    )

    print(
        "Done."
    )
