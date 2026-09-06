
from __future__ import annotations

import bpy
from bpy.types import Node
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)

try:
    from .vfd_manager import VFDManager
except ImportError:
    from vfd_manager import VFDManager


# ----------------------------------------------------------------------
# VFD manager storage
# ----------------------------------------------------------------------

_MANAGERS = {}


def get_vfd_manager(node):
    if node is None:
        return None

    return _MANAGERS.get(id(node))


def create_vfd_manager(node):
    manager = get_vfd_manager(node)

    if manager is not None:
        return manager

    manager = VFDManager()

    _MANAGERS[id(node)] = manager

    return manager


def remove_vfd_manager(node):
    manager = get_vfd_manager(node)

    if manager is not None:
        try:
            manager.stop()
        except Exception:
            pass

        try:
            manager.disconnect()
        except Exception:
            pass

    _MANAGERS.pop(id(node), None)


# ----------------------------------------------------------------------
# Node search
# ----------------------------------------------------------------------

def find_node(name):
    for tree in bpy.data.node_groups:
        node = tree.nodes.get(name)

        if node is not None:
            return node

    return None


# ----------------------------------------------------------------------
# Operators
# ----------------------------------------------------------------------

class VFD_OT_connect(bpy.types.Operator):
    bl_idname = "vfd.connect"
    bl_label = "Connect VFD"

    node_name: StringProperty()

    def execute(self, context):
        node = find_node(self.node_name)

        if node is None:
            self.report({"ERROR"}, "VFD node not found")
            return {"CANCELLED"}

        if node.connect_vfd():
            return {"FINISHED"}

        self.report({"ERROR"}, node.status_text)

        return {"CANCELLED"}


class VFD_OT_disconnect(bpy.types.Operator):
    bl_idname = "vfd.disconnect"
    bl_label = "Disconnect VFD"

    node_name: StringProperty()

    def execute(self, context):
        node = find_node(self.node_name)

        if node is None:
            self.report({"ERROR"}, "VFD node not found")
            return {"CANCELLED"}

        node.disconnect_vfd()

        return {"FINISHED"}


class VFD_OT_execute(bpy.types.Operator):
    bl_idname = "vfd.execute"
    bl_label = "Execute VFD Command"

    node_name: StringProperty()
    command: StringProperty()

    def execute(self, context):
        node = find_node(self.node_name)

        if node is None:
            self.report({"ERROR"}, "VFD node not found")
            return {"CANCELLED"}

        result = node.execute_command(self.command)

        node.console_output = result

        if result.startswith("ERROR"):
            self.report({"ERROR"}, result)
            return {"CANCELLED"}

        return {"FINISHED"}


# ----------------------------------------------------------------------
# VFD Node
# ----------------------------------------------------------------------

class VFDNode(Node):
    bl_idname = "VFDNode"
    bl_label = "VFD"
    bl_icon = "DRIVER"

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    device_name: StringProperty(
        name="Device",
        default="HY01D523B",
    )

    serial_port: StringProperty(
        name="RS-485 Port",
        default="COM3",
    )

    slave_id: IntProperty(
        name="Slave ID",
        default=4,
        min=1,
        max=247,
    )

    baudrate: IntProperty(
        name="Baud Rate",
        default=9600,
        min=1200,
        max=115200,
    )

    # ------------------------------------------------------------------
    # Enable / arm
    # ------------------------------------------------------------------

    enabled: BoolProperty(
        name="Enabled",
        default=True,
    )

    armed: BoolProperty(
        name="ARM",
        default=False,
    )

    # ------------------------------------------------------------------
    # Motor configuration
    #
    # These values are used only for frequency <-> RPM conversion.
    # They are not required by the HY01D523B protocol.
    # ------------------------------------------------------------------

    motor_power_kw: FloatProperty(
        name="Motor Power",
        default=1.5,
        min=0.0,
    )

    motor_voltage: FloatProperty(
        name="Motor Voltage",
        default=220.0,
        min=0.0,
    )

    motor_frequency: FloatProperty(
        name="Rated Frequency",
        default=400.0,
        min=1.0,
    )

    motor_rpm: FloatProperty(
        name="Rated RPM",
        default=24000.0,
        min=1.0,
    )

    minimum_frequency: FloatProperty(
        name="Minimum Frequency",
        default=0.0,
        min=0.0,
    )

    maximum_frequency: FloatProperty(
        name="Maximum Frequency",
        default=400.0,
        min=0.0,
    )

    minimum_rpm: FloatProperty(
        name="Minimum RPM",
        default=0.0,
        min=0.0,
    )

    maximum_rpm: FloatProperty(
        name="Maximum RPM",
        default=24000.0,
        min=0.0,
    )

    # ------------------------------------------------------------------
    # Command properties
    # ------------------------------------------------------------------

    frequency_command: FloatProperty(
        name="Frequency",
        default=0.0,
        min=0.0,
    )

    rpm_command: FloatProperty(
        name="RPM",
        default=0.0,
        min=0.0,
    )

    running_command: BoolProperty(
        name="RUN",
        default=False,
    )

    reverse_command: BoolProperty(
        name="REVERSE",
        default=False,
    )

    reset_command: BoolProperty(
        name="RESET",
        default=False,
    )

    # ------------------------------------------------------------------
    # Status properties
    #
    # Only values currently supported by the manager are treated as
    # meaningful. Current/voltage/power are kept as zero until the
    # actual HY01D523B status protocol is implemented.
    # ------------------------------------------------------------------

    connected: BoolProperty(
        name="Connected",
        default=False,
    )

    running: BoolProperty(
        name="Running",
        default=False,
    )

    reverse: BoolProperty(
        name="Reverse",
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

    actual_frequency: FloatProperty(
        name="Actual Frequency",
        default=0.0,
    )

    actual_rpm: FloatProperty(
        name="Actual RPM",
        default=0.0,
    )

    actual_current: FloatProperty(
        name="Current",
        default=0.0,
    )

    actual_voltage: FloatProperty(
        name="Voltage",
        default=0.0,
    )

    actual_power: FloatProperty(
        name="Power",
        default=0.0,
    )

    status_text: StringProperty(
        name="Status",
        default="Disconnected",
    )

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------

    console_command: StringProperty(
        name="Command",
        default="status",
    )

    console_output: StringProperty(
        name="Output",
        default="Ready",
    )

    # ------------------------------------------------------------------
    # Node initialization
    # ------------------------------------------------------------------

    def init(self, context):
        # Inputs

        frequency = self.inputs.new(
            "NodeSocketFloat",
            "Frequency",
        )
        frequency.default_value = 0.0
        frequency.min_value = 0.0

        rpm = self.inputs.new(
            "NodeSocketFloat",
            "RPM",
        )
        rpm.default_value = 0.0
        rpm.min_value = 0.0

        run = self.inputs.new(
            "NodeSocketBool",
            "RUN",
        )
        run.default_value = False

        reverse = self.inputs.new(
            "NodeSocketBool",
            "REVERSE",
        )
        reverse.default_value = False

        reset = self.inputs.new(
            "NodeSocketBool",
            "RESET",
        )
        reset.default_value = False

        # Outputs

        frequency = self.outputs.new(
            "NodeSocketFloat",
            "Frequency",
        )

        rpm = self.outputs.new(
            "NodeSocketFloat",
            "RPM",
        )

        current = self.outputs.new(
            "NodeSocketFloat",
            "Current",
        )

        voltage = self.outputs.new(
            "NodeSocketFloat",
            "Voltage",
        )

        power = self.outputs.new(
            "NodeSocketFloat",
            "Power",
        )

        connected = self.outputs.new(
            "NodeSocketBool",
            "Connected",
        )

        running = self.outputs.new(
            "NodeSocketBool",
            "Running",
        )

        fault = self.outputs.new(
            "NodeSocketBool",
            "Fault",
        )

        fault_code = self.outputs.new(
            "NodeSocketFloat",
            "Fault Code",
        )

    # ------------------------------------------------------------------
    # Node cleanup
    # ------------------------------------------------------------------

    def free(self):
        remove_vfd_manager(self)

    # ------------------------------------------------------------------
    # Manager
    # ------------------------------------------------------------------

    def get_manager(self):
        return create_vfd_manager(self)

    def update_manager_config(self):
        manager = self.get_manager()

        manager.configure_connection(
            port=self.serial_port,
            slave_id=self.slave_id,
            baudrate=self.baudrate,
            timeout=0.25,
        )

        manager.configure_motor(
            power_kw=self.motor_power_kw,
            voltage_v=self.motor_voltage,
            rated_frequency_hz=self.motor_frequency,
            rated_rpm=self.motor_rpm,
            min_frequency_hz=self.minimum_frequency,
            max_frequency_hz=self.maximum_frequency,
            min_rpm=self.minimum_rpm,
            max_rpm=self.maximum_rpm,
        )

        manager.set_enabled(self.enabled)
        manager.set_armed(self.armed)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect_vfd(self):
        self.update_manager_config()

        manager = self.get_manager()

        result = manager.connect()

        self.update_status()

        return result

    def disconnect_vfd(self):
        manager = self.get_manager()

        manager.disconnect()

        self.update_status()

    # ------------------------------------------------------------------
    # Socket helpers
    # ------------------------------------------------------------------

    def _socket_float(self, name, default):
        socket = self.inputs.get(name)

        if socket is None:
            return default

        try:
            return float(socket.default_value)
        except Exception:
            return default

    def _socket_bool(self, name, default):
        socket = self.inputs.get(name)

        if socket is None:
            return default

        try:
            return bool(socket.default_value)
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Command values
    # ------------------------------------------------------------------

    def get_command(self):
        frequency = float(self.frequency_command)
        rpm = float(self.rpm_command)

        rpm_socket = self.inputs.get("RPM")
        frequency_socket = self.inputs.get("Frequency")

        # RPM input has priority when it is connected.

        if rpm_socket is not None and rpm_socket.is_linked:
            rpm = self._socket_float("RPM", rpm)
            frequency = self.rpm_to_frequency(rpm)

        elif frequency_socket is not None and frequency_socket.is_linked:
            frequency = self._socket_float(
                "Frequency",
                frequency,
            )
            rpm = self.frequency_to_rpm(frequency)

        run = self._socket_bool(
            "RUN",
            self.running_command,
        )

        reverse = self._socket_bool(
            "REVERSE",
            self.reverse_command,
        )

        reset = self._socket_bool(
            "RESET",
            self.reset_command,
        )

        # Safety:
        # disabled or unarmed means RUN must be false.

        if not self.enabled or not self.armed:
            run = False

        return {
            "run": run,
            "frequency": frequency,
            "rpm": rpm,
            "reverse": reverse,
            "reset": reset,
        }

    # ------------------------------------------------------------------
    # Apply node command
    # ------------------------------------------------------------------

    def apply_command(self):
        self.update_manager_config()

        manager = self.get_manager()
        command = self.get_command()

        if not manager.is_connected():
            self.status_text = "Disconnected"
            return False

        # RESET is not implemented in the current HY driver.
        if command["reset"]:
            self.status_text = (
                "RESET is not implemented for HY01D523B"
            )
            return False

        # Set frequency first.

        if not manager.set_frequency(
            command["frequency"]
        ):
            self.update_status()
            return False

        # Then run/stop.

        if command["run"]:
            if not manager.start():
                self.update_status()
                return False
        else:
            if not manager.stop():
                self.update_status()
                return False

        # Direction is part of the RUN command.

        if command["run"]:
            if not manager.set_direction(
                command["reverse"]
            ):
                self.update_status()
                return False

        self.update_status()

        return True

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def update_status(self):
        manager = self.get_manager()

        status = manager.update_status()

        self.connected = bool(status.connected)
        self.running = bool(status.running)
        self.reverse = bool(status.reverse)

        self.fault = bool(status.fault)
        self.fault_code = int(status.fault_code)

        self.actual_frequency = float(
            status.frequency_hz
        )

        self.actual_rpm = float(
            status.rpm
        )

        # These values are intentionally zero until a real
        # HY01D523B measurement/status protocol is implemented.

        self.actual_current = float(
            status.current_a
        )

        self.actual_voltage = float(
            status.voltage_v
        )

        self.actual_power = float(
            status.power_kw
        )

        self.status_text = str(
            status.fault_text
            or status.state.value
        )

        # Update outputs.

        self._set_output(
            "Frequency",
            self.actual_frequency,
        )

        self._set_output(
            "RPM",
            self.actual_rpm,
        )

        self._set_output(
            "Current",
            self.actual_current,
        )

        self._set_output(
            "Voltage",
            self.actual_voltage,
        )

        self._set_output(
            "Power",
            self.actual_power,
        )

        self._set_output(
            "Connected",
            self.connected,
        )

        self._set_output(
            "Running",
            self.running,
        )

        self._set_output(
            "Fault",
            self.fault,
        )

        self._set_output(
            "Fault Code",
            self.fault_code,
        )

        return status

    def _set_output(self, name, value):
        socket = self.outputs.get(name)

        if socket is None:
            return

        try:
            socket.default_value = value
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Frequency / RPM conversion
    # ------------------------------------------------------------------

    def frequency_to_rpm(self, frequency):
        if self.motor_frequency <= 0.0:
            return 0.0

        return (
            float(frequency)
            / self.motor_frequency
            * self.motor_rpm
        )

    def rpm_to_frequency(self, rpm):
        if self.motor_rpm <= 0.0:
            return 0.0

        return (
            float(rpm)
            / self.motor_rpm
            * self.motor_frequency
        )

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------

    def execute_command(self, command):
        manager = self.get_manager()

        text = command.strip()

        if not text:
            return "ERROR: Empty command."

        parts = text.split()

        operation = parts[0].lower()

        # --------------------------------------------------------------
        # CONNECT
        # --------------------------------------------------------------

        if operation == "connect":
            if self.connect_vfd():
                return "OK: Connected"

            return (
                f"ERROR: {self.status_text}"
            )

        # --------------------------------------------------------------
        # DISCONNECT
        # --------------------------------------------------------------

        if operation == "disconnect":
            self.disconnect_vfd()

            return "OK: Disconnected"

        # --------------------------------------------------------------
        # STATUS
        # --------------------------------------------------------------

        if operation == "status":
            self.update_status()

            return (
                f"Connected: {self.connected}\n"
                f"Running: {self.running}\n"
                f"Reverse: {self.reverse}\n"
                f"Frequency: "
                f"{self.actual_frequency:.2f} Hz\n"
                f"RPM: "
                f"{self.actual_rpm:.0f}\n"
                f"Fault: {self.fault}\n"
                f"Fault code: {self.fault_code}\n"
                f"Status: {self.status_text}"
            )

        # --------------------------------------------------------------
        # GET / READ PDxxx
        # --------------------------------------------------------------

        if operation in {"get", "read"}:
            if len(parts) != 2:
                return "ERROR: Use: get PD163"

            parameter_text = parts[1].upper()

            if parameter_text.startswith("PD"):
                parameter_text = parameter_text[2:]

            try:
                parameter = int(parameter_text)
            except ValueError:
                return (
                    "ERROR: Invalid parameter. "
                    "Use PD000-PD182."
                )

            if parameter < 0 or parameter > 182:
                return (
                    "ERROR: Parameter must be "
                    "PD000-PD182."
                )

            if not manager.is_connected():
                return "ERROR: VFD is disconnected."

            value = manager.read_parameter(parameter)

            if value is None:
                return (
                    f"ERROR: {manager.last_error()}"
                )

            result = (
                f"OK: PD{parameter:03d} = {value}"
            )

            return result

        # --------------------------------------------------------------
        # SET / WRITE PDxxx value
        # --------------------------------------------------------------

        if operation in {"set", "write"}:
            if len(parts) != 3:
                return "ERROR: Use: set PD163 4"

            parameter_text = parts[1].upper()

            if parameter_text.startswith("PD"):
                parameter_text = parameter_text[2:]

            try:
                parameter = int(parameter_text)
                value = int(parts[2])
            except ValueError:
                return (
                    "ERROR: Invalid parameter or value."
                )

            if parameter < 0 or parameter > 182:
                return (
                    "ERROR: Parameter must be "
                    "PD000-PD182."
                )

            if value < 0 or value > 65535:
                return (
                    "ERROR: Value must be 0-65535."
                )

            if not manager.is_connected():
                return "ERROR: VFD is disconnected."

            if not manager.write_parameter(
                parameter,
                value,
            ):
                return (
                    f"ERROR: {manager.last_error()}"
                )

            return (
                f"OK: PD{parameter:03d} = {value}"
            )

        # --------------------------------------------------------------
        # START / RUN
        # --------------------------------------------------------------

        if operation in {"start", "run"}:
            if not self.enabled:
                return "ERROR: VFD is disabled."

            if not self.armed:
                return "ERROR: VFD is not armed."

            if not manager.is_connected():
                return "ERROR: VFD is disconnected."

            if manager.start():
                self.update_status()
                return "OK: Started"

            return (
                f"ERROR: {manager.last_error()}"
            )

        # --------------------------------------------------------------
        # STOP / HALT
        # --------------------------------------------------------------

        if operation in {"stop", "halt"}:
            if not manager.is_connected():
                return "ERROR: VFD is disconnected."

            if manager.stop():
                self.update_status()
                return "OK: Stopped"

            return (
                f"ERROR: {manager.last_error()}"
            )

        # --------------------------------------------------------------
        # FREQUENCY
        # --------------------------------------------------------------

        if operation in {"freq", "frequency"}:
            if len(parts) != 2:
                return "ERROR: Use: freq 200"

            try:
                frequency = float(parts[1])
            except ValueError:
                return "ERROR: Invalid frequency."

            if manager.set_frequency(
                frequency
            ):
                self.update_status()

                return (
                    f"OK: Frequency = "
                    f"{frequency:.2f} Hz"
                )

            return (
                f"ERROR: {manager.last_error()}"
            )

        # --------------------------------------------------------------
        # FORWARD
        # --------------------------------------------------------------

        if operation in {"forward", "fwd"}:
            if not self.enabled:
                return "ERROR: VFD is disabled."

            if not self.armed:
                return "ERROR: VFD is not armed."

            if not manager.is_connected():
                return "ERROR: VFD is disconnected."

            if manager.set_direction(False):
                self.update_status()
                return "OK: Forward"

            return (
                f"ERROR: {manager.last_error()}"
            )

        # --------------------------------------------------------------
        # REVERSE
        # --------------------------------------------------------------

        if operation in {"reverse", "rev"}:
            if not self.enabled:
                return "ERROR: VFD is disabled."

            if not self.armed:
                return "ERROR: VFD is not armed."

            if not manager.is_connected():
                return "ERROR: VFD is disconnected."

            if manager.set_direction(True):
                self.update_status()
                return "OK: Reverse"

            return (
                f"ERROR: {manager.last_error()}"
            )

        # --------------------------------------------------------------
        # RESET
        # --------------------------------------------------------------

        if operation == "reset":
            return (
                "ERROR: RESET is not implemented "
                "for HY01D523B."
            )

        # --------------------------------------------------------------
        # ENABLE
        # --------------------------------------------------------------

        if operation == "enable":
            self.enabled = True
            self.update_manager_config()

            return "OK: Enabled"

        # --------------------------------------------------------------
        # DISABLE
        # --------------------------------------------------------------

        if operation == "disable":
            self.enabled = False

            manager.set_enabled(False)

            return "OK: Disabled"

        # --------------------------------------------------------------
        # ARM
        # --------------------------------------------------------------

        if operation == "arm":
            self.armed = True
            self.update_manager_config()

            return "OK: Armed"

        # --------------------------------------------------------------
        # DISARM
        # --------------------------------------------------------------

        if operation in {"disarm", "unarm"}:
            self.armed = False

            manager.set_armed(False)

            return "OK: Disarmed"

        # --------------------------------------------------------------
        # HELP
        # --------------------------------------------------------------

        if operation == "help":
            return (
                "Commands:\n"
                "  connect\n"
                "  disconnect\n"
                "  status\n"
                "  start\n"
                "  run\n"
                "  stop\n"
                "  halt\n"
                "  forward\n"
                "  reverse\n"
                "  freq 200\n"
                "  get PD163\n"
                "  read PD163\n"
                "  set PD163 4\n"
                "  write PD163 4\n"
                "  enable\n"
                "  disable\n"
                "  arm\n"
                "  disarm\n"
                "  help"
            )

        return (
            f"ERROR: Unknown command: "
            f"{operation}"
        )

    # ------------------------------------------------------------------
    # Blender UI
    # ------------------------------------------------------------------

    def draw_buttons(self, context, layout):
        # Connection

        box = layout.box()

        box.label(text="Connection")

        box.prop(self, "device_name")
        box.prop(self, "serial_port")
        box.prop(self, "slave_id")
        box.prop(self, "baudrate")

        row = box.row(align=True)

        connect = row.operator(
            "vfd.connect",
            text="Connect",
        )
        connect.node_name = self.name

        disconnect = row.operator(
            "vfd.disconnect",
            text="Disconnect",
        )
        disconnect.node_name = self.name

        # Safety

        box = layout.box()

        box.label(text="Control")

        box.prop(self, "enabled")
        box.prop(self, "armed")

        # Command

        box = layout.box()

        box.label(text="Command")

        box.prop(
            self,
            "frequency_command",
        )

        box.prop(
            self,
            "rpm_command",
        )

        box.prop(
            self,
            "running_command",
        )

        box.prop(
            self,
            "reverse_command",
        )

        row = box.row()

        row.operator(
            "vfd.execute",
            text="Apply Command",
        ).node_name = self.name

        # Status

        box = layout.box()

        box.label(text="Status")

        box.label(
            text=f"Connection: "
            f"{'Connected' if self.connected else 'Disconnected'}"
        )

        box.label(
            text=f"Running: "
            f"{'YES' if self.running else 'NO'}"
        )

        box.label(
            text=f"Direction: "
            f"{'Reverse' if self.reverse else 'Forward'}"
        )

        box.label(
            text=f"Frequency: "
            f"{self.actual_frequency:.2f} Hz"
        )

        box.label(
            text=f"RPM: "
            f"{self.actual_rpm:.0f}"
        )

        box.label(
            text=f"Status: "
            f"{self.status_text}"
        )

        # Console

        box = layout.box()

        box.label(text="Console")

        box.prop(
            self,
            "console_command",
            text="",
        )

        operator = box.operator(
            "vfd.execute",
            text="Execute",
        )

        operator.node_name = self.name
        operator.command = self.console_command

        box.label(
            text=self.console_output,
        )

    # ------------------------------------------------------------------
    # Blender node update
    # ------------------------------------------------------------------

    def update(self):
        """
        Called by Blender when node properties change.

        We deliberately do not send commands automatically here.
        Communication with the VFD should happen explicitly through
        Apply Command or the console.
        """
        pass


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------

classes = (
    VFDNode,
    VFD_OT_connect,
    VFD_OT_disconnect,
    VFD_OT_execute,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if not hasattr(
        bpy.types,
        "VFDNodeTree",
    ):
        pass


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
