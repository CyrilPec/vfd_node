from __future__ import annotations

import re

import bpy
from bpy.types import Node, NodeSocket
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
try:
    from .huanyang_vfd import HuanyangVFD, HuanyangConfig, PySerialTransport
except ImportError:
    from huanyang_vfd import HuanyangVFD, HuanyangConfig, PySerialTransport
_VFD_DRIVERS = {}


# ============================================================================
# RUNTIME DRIVER REGISTRY
# ============================================================================
#
# Blender Node properties cannot store arbitrary Python objects.
#
# The actual VFD driver will therefore be attached at runtime.
#
# The next step will create/attach the ModbusVFD object here.
#
# Key:
#     id(node)
#
# Value:
#     actual VFD driver object
#
# don't add empty lines to code and make it more as human language text format, but readeble. it will make code smaller as i have big monitor and want less scroll.
# ============================================================================

_RUNTIME_DRIVERS = {}


def attach_vfd_driver(node, driver):
    """
    Attach a runtime VFD driver to a Blender node.

    The driver is NOT stored inside the .blend file.
    It exists only while Blender is running.
    """

    if node is None:
        return

    if driver is None:
        _RUNTIME_DRIVERS.pop(id(node), None)
        return

    _RUNTIME_DRIVERS[id(node)] = driver


def detach_vfd_driver(node):
    """
    Remove the runtime VFD driver from a node.
    """

    if node is None:
        return

    _RUNTIME_DRIVERS.pop(id(node), None)


def get_vfd_driver(node):
    """
    Return the runtime driver assigned to a node.
    """

    if node is None:
        return None

    return _RUNTIME_DRIVERS.get(id(node))

def get_vfd_driver(node):
    driver = _VFD_DRIVERS.get(id(node))
    if driver is not None:
        return driver
    transport = PySerialTransport(
        port=node.serial_port,
        baudrate=node.baudrate,
        timeout=0.2,
    )
    config = HuanyangConfig(
        slave_id=node.slave_id,
        baudrate=node.baudrate,
        timeout=0.2,
        bytesize=8,
        parity="N",
        stopbits=1,
    )
    driver = HuanyangVFD(
        transport=transport,
        config=config,
    )
    _VFD_DRIVERS[id(node)] = driver
    node.driver_name = driver.name
    return driver
def release_vfd_driver(node):
    driver = _VFD_DRIVERS.pop(id(node), None)
    if driver is not None:
        try:
            driver.disconnect()
        except Exception:
            pass

# ============================================================================
# VFD CONSOLE OPERATOR
# ============================================================================


class VFD_OT_console_execute(bpy.types.Operator):
    bl_idname = "vfd.console_execute"
    bl_label = "Execute VFD Command"
    bl_description = "Execute the command entered in the VFD Console"

    node_name: StringProperty()

       def execute(self, context):
        node = None
        for node_group in bpy.data.node_groups:
            candidate = node_group.nodes.get(self.node_name)
            if candidate is not None:
                node = candidate
                break
        if node is None:
            self.report({"ERROR"}, "VFD node not found")
            return {"CANCELLED"}
        command = node.console_command.strip()
        if not command:
            node.console_output = "ERROR: Empty command."
            return {"CANCELLED"}
        try:
            node.console_output = node.execute_console_command(command)
            return {"FINISHED"}
        except Exception as exc:
            node.console_output = f"ERROR: {type(exc).__name__}: {exc}"
            return {"CANCELLED"}


        # ---------------------------------------------------------------------
        # Execute through the node.
        # ---------------------------------------------------------------------

        command = node.console_command.strip()

        if not command:

            node.console_output = "ERROR: Empty command."

            return {"CANCELLED"}

        try:

            result = node.execute_console_command(command)

            node.console_output = str(result)

            return {"FINISHED"}

        except Exception as exc:

            node.console_output = (
                f"ERROR: {type(exc).__name__}: {exc}"
            )

            return {"CANCELLED"}


# ============================================================================
# VFD VALUE SOCKET
# ============================================================================


class VFDValueSocket(NodeSocket):

    bl_idname = "VFDValueSocket"
    bl_label = "VFD Value"

    def draw(
        self,
        context,
        layout,
        node,
        text,
    ):
        layout.label(
            text=text,
        )

    def draw_color(
        self,
        context,
        node,
    ):
        return (
            0.95,
            0.45,
            0.05,
            1.0,
        )

    @classmethod
    def draw_color_simple(cls):
        return (
            0.95,
            0.45,
            0.05,
            1.0,
        )


# ============================================================================
# VFD STATUS SOCKET
# ============================================================================


class VFDStatusSocket(NodeSocket):

    bl_idname = "VFDStatusSocket"
    bl_label = "VFD Status"

    def draw(
        self,
        context,
        layout,
        node,
        text,
    ):
        layout.label(
            text=text,
        )

    def draw_color(
        self,
        context,
        node,
    ):
        return (
            0.20,
            0.80,
            0.30,
            1.0,
        )

    @classmethod
    def draw_color_simple(cls):
        return (
            0.20,
            0.80,
            0.30,
            1.0,
        )


# ============================================================================
# VFD NODE
# ============================================================================


class VFDNode(Node):

    bl_idname = "VFDNode"
    bl_label = "VFD"
    bl_icon = "DRIVER"

    # ------------------------------------------------------------------------
    # GENERAL
    # ------------------------------------------------------------------------

    enabled: BoolProperty(
        name="Enabled",
        description="Enable this VFD node",
        default=True,
    )

    armed: BoolProperty(
        name="ARM",
        description="Allow the node to command the VFD",
        default=False,
    )

    # ------------------------------------------------------------------------
    # DEVICE
    # ------------------------------------------------------------------------

    device_name: StringProperty(
        name="Device",
        description="VFD device name",
        default="VFD",
    )

    driver_name: StringProperty(
        name="Driver",
        description="Driver currently assigned to this VFD",
        default="Not connected",
    )

    slave_id: IntProperty(
        name="Slave ID",
        description="Protocol device address",
        default=1,
        min=0,
        max=247,
    )

    # ------------------------------------------------------------------------
    # SERIAL
    # ------------------------------------------------------------------------

    serial_port: StringProperty(
        name="Serial Port",
        description="RS-485 serial port",
        default="COM3",
    )

    baudrate: IntProperty(
        name="Baud Rate",
        description="RS-485 baud rate",
        default=9600,
        min=1200,
        max=115200,
    )

    driver_model: StringProperty(
        name="Driver",
        default="HY01D523B",
    )

    # ------------------------------------------------------------------------
    # MOTOR
    # ------------------------------------------------------------------------

    motor_power_kw: FloatProperty(
        name="Power",
        description="Motor rated power",
        default=1.5,
        min=0.0,
        soft_max=100.0,
    )

    motor_voltage: FloatProperty(
        name="Voltage",
        description="Motor rated voltage",
        default=220.0,
        min=0.0,
        soft_max=1000.0,
    )

    motor_frequency: FloatProperty(
        name="Rated Frequency",
        description="Motor rated frequency",
        default=400.0,
        min=1.0,
        soft_max=1000.0,
    )

    motor_rpm: FloatProperty(
        name="Rated RPM",
        description="Motor rated RPM",
        default=24000.0,
        min=0.0,
        soft_max=100000.0,
    )

    # ------------------------------------------------------------------------
    # LIMITS
    # ------------------------------------------------------------------------

    minimum_frequency: FloatProperty(
        name="Min Frequency",
        description="Minimum allowed frequency",
        default=0.0,
        min=0.0,
        soft_max=1000.0,
    )

    maximum_frequency: FloatProperty(
        name="Max Frequency",
        description="Maximum allowed frequency",
        default=400.0,
        min=1.0,
        soft_max=1000.0,
    )

    # ------------------------------------------------------------------------
    # COMMAND VALUES
    # ------------------------------------------------------------------------

    frequency_command: FloatProperty(
        name="Frequency",
        description="Requested VFD frequency",
        default=0.0,
        min=0.0,
        soft_max=1000.0,
    )

    speed_command: FloatProperty(
        name="RPM",
        description="Requested spindle speed",
        default=0.0,
        min=0.0,
        soft_max=100000.0,
    )

    running_command: BoolProperty(
        name="Run",
        description="Requested run state",
        default=False,
    )

    reverse_command: BoolProperty(
        name="Reverse",
        description="Requested reverse direction",
        default=False,
    )

    reset_command: BoolProperty(
        name="Reset",
        description="Request VFD fault reset",
        default=False,
    )

    # ------------------------------------------------------------------------
    # ACTUAL VALUES
    # ------------------------------------------------------------------------

    actual_frequency: FloatProperty(
        name="Actual Frequency",
        default=0.0,
    )

    actual_rpm: FloatProperty(
        name="Actual RPM",
        default=0.0,
    )

    actual_current: FloatProperty(
        name="Actual Current",
        default=0.0,
    )

    actual_voltage: FloatProperty(
        name="Actual Voltage",
        default=0.0,
    )

    actual_power: FloatProperty(
        name="Actual Power",
        default=0.0,
    )

    # ------------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------------

    connected: BoolProperty(
        name="Connected",
        default=False,
    )

    running: BoolProperty(
        name="Running",
        default=False,
    )

    fault: BoolProperty(
        name="Fault",
        default=False,
    )

    fault_code: IntProperty(
        name="Fault Code",
        default=0,
    )

    status_text: StringProperty(
        name="Status",
        default="Disconnected",
    )

    # ------------------------------------------------------------------------
    # VFD CONSOLE
    # ------------------------------------------------------------------------

    console_command: StringProperty(
        name="Command",
        description="VFD console command",
        default="get PD142",
    )

    console_output: StringProperty(
        name="Output",
        description="Last VFD console result",
        default="Ready.",
    )

    # =========================================================================
    # INIT
    # =========================================================================

    def init(
        self,
        context,
    ):

        # ---------------------------------------------------------------------
        # INPUTS
        # ---------------------------------------------------------------------

        self.inputs.new(
            "VFDValueSocket",
            "Frequency",
        )

        self.inputs.new(
            "VFDValueSocket",
            "RPM",
        )

        self.inputs.new(
            "NodeSocketBool",
            "Run",
        )

        self.inputs.new(
            "NodeSocketBool",
            "Reverse",
        )

        self.inputs.new(
            "NodeSocketBool",
            "Reset",
        )

        # ---------------------------------------------------------------------
        # OUTPUTS
        # ---------------------------------------------------------------------

        self.outputs.new(
            "VFDValueSocket",
            "Frequency",
        )

        self.outputs.new(
            "VFDValueSocket",
            "RPM",
        )

        self.outputs.new(
            "VFDValueSocket",
            "Current",
        )

        self.outputs.new(
            "VFDValueSocket",
            "Voltage",
        )

        self.outputs.new(
            "VFDValueSocket",
            "Power",
        )

        self.outputs.new(
            "VFDStatusSocket",
            "Connected",
        )

        self.outputs.new(
            "VFDStatusSocket",
            "Running",
        )

        self.outputs.new(
            "VFDStatusSocket",
            "Fault",
        )

        self.outputs.new(
            "VFDStatusSocket",
            "Fault Code",
        )

    # =========================================================================
    # RUNTIME DRIVER
    # =========================================================================

    def get_driver(self):
        """
        Return the runtime VFD driver assigned to this node.
        """

        return get_vfd_driver(self)

    # =========================================================================
    # FREQUENCY / RPM CONVERSION
    # =========================================================================

    def frequency_to_rpm(
        self,
        frequency,
    ):

        if self.motor_frequency <= 0.0:
            return 0.0

        return (
            float(frequency)
            / float(self.motor_frequency)
            * float(self.motor_rpm)
        )

    def rpm_to_frequency(
        self,
        rpm,
    ):

        if self.motor_rpm <= 0.0:
            return 0.0

        return (
            float(rpm)
            / float(self.motor_rpm)
            * float(self.motor_frequency)
        )

    # =========================================================================
    # COMMAND LIMITING
    # =========================================================================

    def clamp_frequency(
        self,
        frequency,
    ):

        low = min(
            self.minimum_frequency,
            self.maximum_frequency,
        )

        high = max(
            self.minimum_frequency,
            self.maximum_frequency,
        )

        return max(
            low,
            min(
                float(frequency),
                high,
            ),
        )

    # =========================================================================
    # UNIVERSAL COMMAND API
    # =========================================================================

    def get_command(self):

        frequency = self.frequency_command

        # RPM input has priority when connected.

        rpm_socket = self.inputs.get("RPM")

        if rpm_socket is not None:

            if rpm_socket.is_linked:

                try:

                    rpm = float(
                        rpm_socket.default_value
                    )

                    frequency = self.rpm_to_frequency(
                        rpm
                    )

                except Exception:
                    pass

        frequency = self.clamp_frequency(
            frequency
        )

        return {
            "enabled": bool(
                self.enabled
            ),

            "armed": bool(
                self.armed
            ),

            "run": bool(
                self.running_command
            ),

            "reverse": bool(
                self.reverse_command
            ),

            "reset": bool(
                self.reset_command
            ),

            "frequency": float(
                frequency
            ),

            "rpm": float(
                self.frequency_to_rpm(
                    frequency
                )
            ),
        }

    # =========================================================================
    # DRIVER API
    # =========================================================================

    def driver_update(
        self,
        driver,
    ):

        if driver is None:
            return None

        command = self.get_command()

        return command

    # =========================================================================
    # CONSOLE
    # =========================================================================

       def execute_console_command(self, command):
        parts = command.strip().split()
        if not parts:
            return "ERROR: Empty command."
        operation = parts[0].lower()
        if operation == "get":
            if len(parts) != 2:
                return "ERROR: Use: get PDxxx"
            parameter = parts[1].upper()
            if not self._valid_parameter(parameter):
                return "ERROR: Parameter must be PD000-PD999."
            driver = self.get_driver()
            if driver is None:
                return "ERROR: VFD driver unavailable."
            value = driver.get_parameter(int(parameter[2:]))
            if value is None:
                return f"ERROR: Cannot read {parameter}: {driver.last_error}"
            return f"{parameter} = {value}"
        if operation == "set":
            if len(parts) != 3:
                return "ERROR: Use: set PDxxx VALUE"
            parameter = parts[1].upper()
            if not self._valid_parameter(parameter):
                return "ERROR: Parameter must be PD000-PD999."
            try:
                value = int(float(parts[2]))
            except ValueError:
                return f"ERROR: Invalid value: {parts[2]}"
            if not self.armed:
                return "ERROR: VFD is not ARMED."
            driver = self.get_driver()
            if driver is None:
                return "ERROR: VFD driver unavailable."
            if driver.set_parameter(int(parameter[2:]), value):
                return f"OK: {parameter} = {value}"
            return f"ERROR: Cannot write {parameter}: {driver.last_error}"
        if operation == "status":
            driver = self.get_driver()
            if driver is None:
                return "ERROR: VFD driver unavailable."
            status = driver.get_status()
            if status is None:
                return f"ERROR: {driver.last_error}"
            self.connected = bool(status.connected)
            self.running = bool(status.running)
            self.actual_frequency = float(status.frequency_hz)
            self.actual_rpm = float(status.rpm)
            self.actual_current = float(status.current_a)
            self.actual_voltage = float(status.voltage_v)
            self.status_text = str(status.state)
            return (
                f"Connected: {status.connected}\n"
                f"Running: {status.running}\n"
                f"Frequency: {status.frequency_hz:.2f} Hz\n"
                f"RPM: {status.rpm:.0f}\n"
                f"Current: {status.current_a:.2f} A\n"
                f"Voltage: {status.voltage_v:.1f} V"
            )
        if operation == "start":
            if not self.armed:
                return "ERROR: VFD is not ARMED."
            driver = self.get_driver()
            if driver is None:
                return "ERROR: VFD driver unavailable."
            if driver.start():
                self.running = True
                return "OK: START"
            return f"ERROR: START failed: {driver.last_error}"
        if operation == "stop":
            driver = self.get_driver()
            if driver is None:
                return "ERROR: VFD driver unavailable."
            if driver.stop():
                self.running = False
                return "OK: STOP"
            return f"ERROR: STOP failed: {driver.last_error}"
        if operation in ("freq", "frequency"):
            if len(parts) != 2:
                return "ERROR: Use: freq VALUE"
            try:
                frequency = float(parts[1])
            except ValueError:
                return f"ERROR: Invalid frequency: {parts[1]}"
            if not self.armed:
                return "ERROR: VFD is not ARMED."
            driver = self.get_driver()
            if driver is None:
                return "ERROR: VFD driver unavailable."
            if driver.set_frequency(frequency):
                self.frequency_command = frequency
                return f"OK: FREQUENCY {frequency:g} Hz"
            return f"ERROR: FREQUENCY failed: {driver.last_error}"
        return f"ERROR: Unknown command: {command}"
    @staticmethod
    def _valid_parameter(parameter):
        return (
            len(parameter) == 5
            and parameter[:2] == "PD"
            and parameter[2:].isdigit()
        )
    def get_driver(self):
        return get_vfd_driver(self)


        # ---------------------------------------------------------------------
        # GET PARAMETER
        # ---------------------------------------------------------------------

        if operation == "get":

            if len(parts) != 2:

                return (
                    "ERROR: Use: get PDxxx"
                )

            parameter = parts[1].upper()

            if not self._valid_parameter_name(
                parameter
            ):

                return (
                    "ERROR: Invalid parameter. "
                    "Use PD000-PD999."
                )

            if driver is None:

                return (
                    "ERROR: No VFD driver attached."
                )

            return self._driver_get_parameter(
                driver,
                parameter,
            )

        # ---------------------------------------------------------------------
        # SET PARAMETER
        # ---------------------------------------------------------------------

        if operation == "set":

            if len(parts) != 3:

                return (
                    "ERROR: Use: set PDxxx VALUE"
                )

            parameter = parts[1].upper()
            value_text = parts[2]

            if not self._valid_parameter_name(
                parameter
            ):

                return (
                    "ERROR: Invalid parameter. "
                    "Use PD000-PD999."
                )

            try:

                value = float(
                    value_text
                )

            except ValueError:

                return (
                    f"ERROR: Invalid value: "
                    f"{value_text}"
                )

            if driver is None:

                return (
                    "ERROR: No VFD driver attached."
                )

            # ---------------------------------------------------------------
            # Writes require ARM.
            # ---------------------------------------------------------------

            if not self.enabled:

                return (
                    "ERROR: VFD node is disabled."
                )

            if not self.armed:

                return (
                    "ERROR: VFD is not ARMED."
                )

            return self._driver_set_parameter(
                driver,
                parameter,
                value,
            )

        # ---------------------------------------------------------------------
        # STATUS
        # ---------------------------------------------------------------------

        if operation == "status":

            return self._console_status()

        # ---------------------------------------------------------------------
        # START
        # ---------------------------------------------------------------------

        if operation == "start":

            if driver is None:

                return (
                    "ERROR: No VFD driver attached."
                )

            if not self.enabled:

                return (
                    "ERROR: VFD node is disabled."
                )

            if not self.armed:

                return (
                    "ERROR: VFD is not ARMED."
                )

            method = getattr(
                driver,
                "start",
                None,
            )

            if method is None:

                return (
                    "ERROR: Driver does not support start()."
                )

            result = method()

            if result:

                self.running = True

                return "OK: START"

            return "ERROR: START failed."

        # ---------------------------------------------------------------------
        # STOP
        # ---------------------------------------------------------------------

        if operation == "stop":

            if driver is None:

                return (
                    "ERROR: No VFD driver attached."
                )

            method = getattr(
                driver,
                "stop",
                None,
            )

            if method is None:

                return (
                    "ERROR: Driver does not support stop()."
                )

            result = method()

            if result:

                self.running = False

                return "OK: STOP"

            return "ERROR: STOP failed."

        # ---------------------------------------------------------------------
        # FREQUENCY
        # ---------------------------------------------------------------------

        if operation in {
            "freq",
            "frequency",
        }:

            if len(parts) != 2:

                return (
                    "ERROR: Use: freq VALUE"
                )

            try:

                frequency = float(
                    parts[1]
                )

            except ValueError:

                return (
                    f"ERROR: Invalid frequency: "
                    f"{parts[1]}"
                )

            frequency = self.clamp_frequency(
                frequency
            )

            if driver is None:

                return (
                    "ERROR: No VFD driver attached."
                )

            if not self.enabled:

                return (
                    "ERROR: VFD node is disabled."
                )

            if not self.armed:

                return (
                    "ERROR: VFD is not ARMED."
                )

            method = getattr(
                driver,
                "set_frequency",
                None,
            )

            if method is None:

                return (
                    "ERROR: Driver does not support "
                    "set_frequency()."
                )

            result = method(
                frequency
            )

            if result:

                self.frequency_command = (
                    frequency
                )

                return (
                    f"OK: FREQUENCY "
                    f"{frequency:g} Hz"
                )

            return (
                "ERROR: Frequency command failed."
            )

        # ---------------------------------------------------------------------
        # UNKNOWN
        # ---------------------------------------------------------------------

        return (
            f"ERROR: Unknown command: "
            f"{command}"
        )

    # =========================================================================
    # CONSOLE PARAMETER HELPERS
    # =========================================================================

    @staticmethod
    def _valid_parameter_name(
        parameter,
    ):

        return bool(
            re.fullmatch(
                r"PD\d{3}",
                str(parameter).upper(),
            )
        )

    def _parameter_number(
        self,
        parameter,
    ):

        return int(
            str(parameter)[2:]
        )

    def _driver_get_parameter(
        self,
        driver,
        parameter,
    ):
        """
        Get an arbitrary PDxxx parameter.

        The preferred future driver API is:

            driver.get_parameter(number)

        If the driver does not provide that API yet, we return a clear
        message instead of inventing a register mapping.
        """

        number = self._parameter_number(
            parameter
        )

        method = getattr(
            driver,
            "get_parameter",
            None,
        )

        if method is None:

            return (
                "ERROR: Driver does not yet "
                "implement get_parameter(). "
                f"Requested {parameter}."
            )

        try:

            value = method(
                number
            )

            return (
                f"{parameter} = {value}"
            )

        except Exception as exc:

            return (
                f"ERROR reading {parameter}: "
                f"{exc}"
            )

    def _driver_set_parameter(
        self,
        driver,
        parameter,
        value,
    ):
        """
        Set an arbitrary PDxxx parameter.

        The preferred driver API is:

            driver.set_parameter(number, value)
        """

        number = self._parameter_number(
            parameter
        )

        method = getattr(
            driver,
            "set_parameter",
            None,
        )

        if method is None:

            return (
                "ERROR: Driver does not yet "
                "implement set_parameter(). "
                f"Requested {parameter} = {value}."
            )

        try:

            result = method(
                number,
                value,
            )

            if result:

                return (
                    f"OK: {parameter} = {value:g}"
                )

            return (
                f"ERROR: Failed to set "
                f"{parameter}."
            )

        except Exception as exc:

            return (
                f"ERROR writing {parameter}: "
                f"{exc}"
            )

    # =========================================================================
    # CONSOLE STATUS
    # =========================================================================

    def _console_status(
        self,
    ):

        driver = self.get_driver()

        lines = [
            f"Device: {self.device_name}",
            f"Driver: {self.driver_name}",
            f"Address: {self.slave_id}",
            f"Connected: {self.connected}",
            f"Running: {self.running}",
            f"Fault: {self.fault}",
        ]

        if driver is None:

            lines.append(
                "Driver object: NOT ATTACHED"
            )

            return "\n".join(
                lines
            )

        is_connected = getattr(
            driver,
            "is_connected",
            None,
        )

        if callable(
            is_connected
        ):

            try:

                lines.append(
                    "Driver connected: "
                    f"{bool(is_connected())}"
                )

            except Exception as exc:

                lines.append(
                    "Driver connection check: "
                    f"ERROR: {exc}"
                )

        return "\n".join(
            lines
        )

    # =========================================================================
    # UI
    # =========================================================================

    def draw_buttons(
        self,
        context,
        layout,
    ):

        # ---------------------------------------------------------------------
        # DEVICE
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="VFD",
            icon="DRIVER",
        )

        box.prop(
            self,
            "device_name",
            text="Name",
        )

        box.label(
            text=f"Driver: {self.driver_name}",
        )

        # ---------------------------------------------------------------------
        # CONNECTION
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="Connection",
            icon="LINKED",
        )

        if self.connected:

            row = box.row()

            row.label(
                text="CONNECTED",
                icon="CHECKMARK",
            )

        else:

            row = box.row()

            row.alert = True

            row.label(
                text="DISCONNECTED",
                icon="ERROR",
            )

        box.prop(
            self,
            "serial_port",
            text="Port",
        )

        box.prop(
            self,
            "baudrate",
            text="Baud",
        )

        box.prop(
            self,
            "slave_id",
            text="Address",
        )

        # ---------------------------------------------------------------------
        # MOTOR
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="Motor",
            icon="MESH_CIRCLE",
        )

        box.prop(
            self,
            "motor_power_kw",
            text="Power",
        )

        box.prop(
            self,
            "motor_voltage",
            text="Voltage",
        )

        box.prop(
            self,
            "motor_frequency",
            text="Rated Hz",
        )

        box.prop(
            self,
            "motor_rpm",
            text="Rated RPM",
        )

        # ---------------------------------------------------------------------
        # LIMITS
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="Frequency Limits",
        )

        box.prop(
            self,
            "minimum_frequency",
            text="Min",
        )

        box.prop(
            self,
            "maximum_frequency",
            text="Max",
        )

        # ---------------------------------------------------------------------
        # COMMAND
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="Command",
            icon="PLAY",
        )

        box.prop(
            self,
            "frequency_command",
            text="Frequency",
        )

        box.label(
            text=(
                f"RPM: "
                f"{self.frequency_to_rpm(self.frequency_command):.0f}"
            ),
        )

        box.prop(
            self,
            "running_command",
            text="RUN",
            toggle=True,
        )

        box.prop(
            self,
            "reverse_command",
            text="REVERSE",
            toggle=True,
        )

        box.prop(
            self,
            "reset_command",
            text="RESET",
        )

        # ---------------------------------------------------------------------
        # VFD CONSOLE
        # ---------------------------------------------------------------------

        box = layout.box()
        box.label(text="VFD Console", icon="CONSOLE")
        box.prop(self, "console_command", text="")
        row = box.row()
        row.scale_y = 1.3
        op = row.operator("vfd.console_execute", text="EXECUTE", icon="PLAY")
        op.node_name = self.name
        box.label(text=self.console_output, icon="INFO")


        output_box = box.box()

        output_box.label(
            text=self.console_output,
        )

        # ---------------------------------------------------------------------
        # CONSOLE HELP
        # ---------------------------------------------------------------------

        help_box = box.box()

        help_box.label(
            text="Examples:",
        )

        help_box.label(
            text="get PD142",
        )

        help_box.label(
            text="set PD142 10",
        )

        help_box.label(
            text="status",
        )

        help_box.label(
            text="freq 100",
        )

        help_box.label(
            text="start / stop",
        )

        # ---------------------------------------------------------------------
        # SAFETY
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="Safety",
            icon="LOCKED",
        )

        box.prop(
            self,
            "enabled",
            text="Enabled",
        )

        row = box.row()

        if self.armed:

            row.alert = True

        row.prop(
            self,
            "armed",
            text=(
                "ARMED"
                if self.armed
                else "ARM"
            ),
            toggle=True,
        )

        # ---------------------------------------------------------------------
        # STATUS
        # ---------------------------------------------------------------------

        box = layout.box()

        box.label(
            text="Status",
            icon="INFO",
        )

        box.label(
            text=self.status_text,
        )

        box.label(
            text=(
                f"Frequency: "
                f"{self.actual_frequency:.1f} Hz"
            ),
        )

        box.label(
            text=(
                f"RPM: "
                f"{self.actual_rpm:.0f}"
            ),
        )

        box.label(
            text=(
                f"Current: "
                f"{self.actual_current:.2f} A"
            ),
        )

        box.label(
            text=(
                f"Voltage: "
                f"{self.actual_voltage:.1f} V"
            ),
        )

        box.label(
            text=(
                f"Power: "
                f"{self.actual_power:.2f} kW"
            ),
        )

        if self.fault:

            row = box.row()

            row.alert = True

            row.label(
                text=(
                    f"FAULT: "
                    f"{self.fault_code}"
                ),
                icon="ERROR",
            )

    # =========================================================================
    # LABEL
    # =========================================================================

    def draw_label(
        self,
    ):

        return (
            f"VFD "
            f"{self.device_name}"
        )


# ============================================================================
# REGISTER CLASSES
# ============================================================================


classes = (
    VFDValueSocket,
    VFDStatusSocket,
    VFD_OT_console_execute,
    VFDNode,
)
