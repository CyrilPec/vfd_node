#dont use empty lines, 
#use english language format of lines ever possible, screen is wide, so less scroling requered.
from __future__ import annotations

import re

import bpy
from bpy.types import Node, NodeSocket
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty

try:
    from .huanyang_vfd import (
        HuanyangVFD,
        HuanyangConfig,
        PySerialTransport,
    )
except ImportError:
    from huanyang_vfd import (
        HuanyangVFD,
        HuanyangConfig,
        PySerialTransport,
    )


_RUNTIME_DRIVERS = {}


def attach_vfd_driver(node, driver):
    if node is None:
        return
    if driver is None:
        _RUNTIME_DRIVERS.pop(id(node), None)
        return
    _RUNTIME_DRIVERS[id(node)] = driver


def detach_vfd_driver(node):
    if node is None:
        return
    _RUNTIME_DRIVERS.pop(id(node), None)


def get_vfd_driver(node):
    if node is None:
        return None
    return _RUNTIME_DRIVERS.get(id(node))


def release_vfd_driver(node):
    driver = get_vfd_driver(node)
    if driver is not None:
        try:
            driver.disconnect()
        except Exception:
            pass
    detach_vfd_driver(node)


class VFDValueSocket(NodeSocket):
    bl_idname = "VFDValueSocket"
    bl_label = "VFD Value"

    value: FloatProperty(
        name="Value",
        default=0.0,
    )

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.95, 0.45, 0.05, 1.0)

    @classmethod
    def draw_color_simple(cls):
        return (0.95, 0.45, 0.05, 1.0)


class VFDStatusSocket(NodeSocket):
    bl_idname = "VFDStatusSocket"
    bl_label = "VFD Status"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.20, 0.80, 0.30, 1.0)

    @classmethod
    def draw_color_simple(cls):
        return (0.20, 0.80, 0.30, 1.0)


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
            node.console_output = (
                f"ERROR: {type(exc).__name__}: {exc}"
            )
            return {"CANCELLED"}


class VFDNode(Node):
    bl_idname = "VFDNode"
    bl_label = "VFD"
    bl_icon = "DRIVER"

    enabled: BoolProperty(
        name="Enabled",
        description="Enable this VFD node",
        default=True,
    )

    armed: BoolProperty(
        name="ARM",
        description="Allow this node to command the VFD",
        default=False,
    )

    device_name: StringProperty(
        name="Device",
        default="VFD",
    )

    driver_name: StringProperty(
        name="Driver",
        default="Not connected",
    )

    slave_id: IntProperty(
        name="Slave ID",
        default=1,
        min=1,
        max=247,
    )

    serial_port: StringProperty(
        name="Serial Port",
        default="COM3",
    )

    baudrate: IntProperty(
        name="Baud Rate",
        default=9600,
        min=1200,
        max=115200,
    )

    driver_model: StringProperty(
        name="Driver Model",
        default="HY01D523B",
    )

    motor_power_kw: FloatProperty(
        name="Power",
        default=1.5,
        min=0.0,
        soft_max=100.0,
    )

    motor_voltage: FloatProperty(
        name="Voltage",
        default=220.0,
        min=0.0,
        soft_max=1000.0,
    )

    motor_frequency: FloatProperty(
        name="Rated Frequency",
        default=400.0,
        min=1.0,
        soft_max=1000.0,
    )

    motor_rpm: FloatProperty(
        name="Rated RPM",
        default=24000.0,
        min=0.0,
        soft_max=100000.0,
    )

    minimum_frequency: FloatProperty(
        name="Min Frequency",
        default=0.0,
        min=0.0,
        soft_max=1000.0,
    )

    maximum_frequency: FloatProperty(
        name="Max Frequency",
        default=400.0,
        min=1.0,
        soft_max=1000.0,
    )

    frequency_command: FloatProperty(
        name="Frequency",
        default=0.0,
        min=0.0,
        soft_max=1000.0,
    )

    speed_command: FloatProperty(
        name="RPM",
        default=0.0,
        min=0.0,
        soft_max=100000.0,
    )

    running_command: BoolProperty(
        name="Run",
        default=False,
    )

    reverse_command: BoolProperty(
        name="Reverse",
        default=False,
    )

    reset_command: BoolProperty(
        name="Reset",
        default=False,
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

    console_command: StringProperty(
        name="Command",
        default="get PD142",
    )

    console_output: StringProperty(
        name="Output",
        default="Ready.",
    )

    def init(self, context):
        self.inputs.new("VFDValueSocket", "Frequency")
        self.inputs.new("VFDValueSocket", "RPM")
        self.inputs.new("NodeSocketBool", "Run")
        self.inputs.new("NodeSocketBool", "Reverse")
        self.inputs.new("NodeSocketBool", "Reset")

        self.outputs.new("VFDValueSocket", "Frequency")
        self.outputs.new("VFDValueSocket", "RPM")
        self.outputs.new("VFDValueSocket", "Current")
        self.outputs.new("VFDValueSocket", "Voltage")
        self.outputs.new("VFDValueSocket", "Power")
        self.outputs.new("VFDStatusSocket", "Connected")
        self.outputs.new("VFDStatusSocket", "Running")
        self.outputs.new("VFDStatusSocket", "Fault")
        self.outputs.new("VFDStatusSocket", "Fault Code")

    def copy(self, node):
        detach_vfd_driver(self)

    def free(self):
        release_vfd_driver(self)

    def get_driver(self):
        driver = get_vfd_driver(self)

        if driver is None:
            driver = self._create_driver()

        return driver

    def _create_driver(self):
        driver = get_vfd_driver(self)

        if driver is not None:
            return driver

        transport = PySerialTransport(
            port=self.serial_port,
            baudrate=self.baudrate,
            timeout=0.2,
        )

        config = HuanyangConfig(
            slave_id=self.slave_id,
            baudrate=self.baudrate,
            timeout=0.2,
            bytesize=8,
            parity="N",
            stopbits=1,
        )

        driver = HuanyangVFD(
            transport=transport,
            config=config,
        )

        attach_vfd_driver(self, driver)
        self.driver_name = getattr(
            driver,
            "name",
            "Huanyang HY",
        )

        return driver

    def connect(self):
        driver = self.get_driver()

        if driver is None:
            self.status_text = "Driver unavailable"
            return False

        try:
            result = bool(driver.connect())

            self.connected = result

            if result:
                self.status_text = "Connected"
                self.driver_name = getattr(
                    driver,
                    "name",
                    "Huanyang HY",
                )
            else:
                self.status_text = getattr(
                    driver,
                    "last_error",
                    "Connection failed",
                )

            return result

        except Exception as exc:
            self.connected = False
            self.status_text = str(exc)
            return False

    def disconnect(self):
        driver = get_vfd_driver(self)

        if driver is not None:
            try:
                driver.disconnect()
            except Exception:
                pass

        self.connected = False
        self.running = False
        self.status_text = "Disconnected"

    def frequency_to_rpm(self, frequency):
        if self.motor_frequency <= 0.0:
            return 0.0

        return (
            float(frequency)
            / float(self.motor_frequency)
            * float(self.motor_rpm)
        )

    def rpm_to_frequency(self, rpm):
        if self.motor_rpm <= 0.0:
            return 0.0

        return (
            float(rpm)
            / float(self.motor_rpm)
            * float(self.motor_frequency)
        )

    def clamp_frequency(self, frequency):
        low = float(self.minimum_frequency)
        high = float(self.maximum_frequency)

        if high < low:
            low, high = high, low

        return max(
            low,
            min(float(frequency), high),
        )

    def _read_socket_value(self, socket, default=0.0):
        if socket is None:
            return default

        try:
            if hasattr(socket, "value"):
                return float(socket.value)
        except Exception:
            pass

        try:
            if hasattr(socket, "default_value"):
                return float(socket.default_value)
        except Exception:
            pass

        try:
            if socket.is_linked:
                source = socket.links[0].from_socket

                if hasattr(source, "value"):
                    return float(source.value)

                if hasattr(source, "default_value"):
                    return float(source.default_value)
        except Exception:
            pass

        return default

    def _read_socket_bool(self, socket, default=False):
        if socket is None:
            return default

        try:
            if socket.is_linked:
                source = socket.links[0].from_socket

                if hasattr(source, "default_value"):
                    return bool(source.default_value)

                if hasattr(source, "value"):
                    return bool(source.value)
        except Exception:
            pass

        try:
            return bool(socket.default_value)
        except Exception:
            return default

    def get_command(self):
        frequency = float(self.frequency_command)

        frequency_socket = self.inputs.get("Frequency")
        rpm_socket = self.inputs.get("RPM")

        if rpm_socket is not None and rpm_socket.is_linked:
            rpm = self._read_socket_value(
                rpm_socket,
                self.speed_command,
            )
            frequency = self.rpm_to_frequency(rpm)

        elif frequency_socket is not None and frequency_socket.is_linked:
            frequency = self._read_socket_value(
                frequency_socket,
                self.frequency_command,
            )

        frequency = self.clamp_frequency(frequency)

        run = self._read_socket_bool(
            self.inputs.get("Run"),
            self.running_command,
        )

        reverse = self._read_socket_bool(
            self.inputs.get("Reverse"),
            self.reverse_command,
        )

        reset = self._read_socket_bool(
            self.inputs.get("Reset"),
            self.reset_command,
        )

        if not self.enabled or not self.armed:
            run = False

        return {
            "enabled": bool(self.enabled),
            "armed": bool(self.armed),
            "run": bool(run),
            "reverse": bool(reverse),
            "reset": bool(reset),
            "frequency": float(frequency),
            "rpm": float(
                self.frequency_to_rpm(frequency)
            ),
        }

    def driver_update(self, driver=None):
        if driver is None:
            driver = self.get_driver()

        if driver is None:
            return False

        command = self.get_command()

        if not command["enabled"] or not command["armed"]:
            return self._apply_stop(driver)

        if not self.connected:
            if not self.connect():
                return False

        try:
            if command["reset"]:
                reset = getattr(
                    driver,
                    "reset_fault",
                    None,
                )

                if callable(reset):
                    reset()

            set_frequency = getattr(
                driver,
                "set_frequency",
                None,
            )

            if callable(set_frequency):
                if not set_frequency(
                    command["frequency"]
                ):
                    self._set_driver_error(driver)
                    return False

            set_direction = getattr(
                driver,
                "set_direction",
                None,
            )

            if callable(set_direction):
                try:
                    from .vfd_manager import VFDDirection
                except ImportError:
                    from vfd_manager import VFDDirection

                direction = (
                    VFDDirection.REVERSE
                    if command["reverse"]
                    else VFDDirection.FORWARD
                )

                if not set_direction(direction):
                    self._set_driver_error(driver)
                    return False

            if command["run"]:
                method = getattr(
                    driver,
                    "start",
                    None,
                )

                if method is None:
                    self.status_text = (
                        "Driver has no start()"
                    )
                    return False

                if not method():
                    self._set_driver_error(driver)
                    return False

                self.running = True

            else:
                if not self._apply_stop(driver):
                    return False

            self.update_status()

            return True

        except Exception as exc:
            self.status_text = str(exc)
            self.connected = False
            return False

    def _apply_stop(self, driver):
        stop = getattr(
            driver,
            "stop",
            None,
        )

        if stop is None:
            self.status_text = (
                "Driver has no stop()"
            )
            return False

        try:
            result = bool(stop())

            if result:
                self.running = False
                self.status_text = "Stopped"

            else:
                self._set_driver_error(driver)

            return result

        except Exception as exc:
            self.status_text = str(exc)
            return False

    def _set_driver_error(self, driver):
        self.status_text = getattr(
            driver,
            "last_error",
            "VFD command failed",
        )

    def update_status(self):
        driver = self.get_driver()

        if driver is None:
            self.connected = False
            self.running = False
            self.status_text = "No driver"
            return

        try:
            status = driver.get_status()

            if status is None:
                self.connected = False
                self.status_text = "No status"
                return

            self.connected = bool(
                status.connected
            )
            self.running = bool(
                status.running
            )

            self.actual_frequency = float(
                getattr(
                    status,
                    "frequency_hz",
                    0.0,
                )
            )

            self.actual_rpm = float(
                getattr(
                    status,
                    "rpm",
                    0.0,
                )
            )

            self.actual_current = float(
                getattr(
                    status,
                    "current_a",
                    0.0,
                )
            )

            self.actual_voltage = float(
                getattr(
                    status,
                    "voltage_v",
                    0.0,
                )
            )

            self.fault = bool(
                getattr(
                    status,
                    "fault",
                    False,
                )
            )

            self.fault_code = int(
                getattr(
                    status,
                    "fault_code",
                    0,
                )
            )

            state = getattr(
                status,
                "state",
                None,
            )

            self.status_text = (
                getattr(
                    state,
                    "value",
                    str(state),
                )
                if state is not None
                else "Unknown"
            )

            if self.fault:
                self.status_text = (
                    f"FAULT {self.fault_code}"
                )

        except Exception as exc:
            self.connected = False
            self.status_text = str(exc)

    def _valid_parameter_name(self, parameter):
        return bool(
            re.fullmatch(
                r"PD\d{3}",
                str(parameter).upper(),
            )
        )

    def _parameter_number(self, parameter):
        return int(
            str(parameter).upper()[2:]
        )

    def execute_console_command(self, command):
        parts = command.strip().split()

        if not parts:
            return "ERROR: Empty command."

        operation = parts[0].lower()

        if operation == "connect":
            return (
                "OK: CONNECTED"
                if self.connect()
                else f"ERROR: {self.status_text}"
            )

        if operation == "disconnect":
            self.disconnect()
            return "OK: DISCONNECTED"

        if operation == "status":
            self.update_status()

            return "\n".join(
                (
                    f"Device: {self.device_name}",
                    f"Driver: {self.driver_name}",
                    f"Connected: {self.connected}",
                    f"Running: {self.running}",
                    f"Frequency: {self.actual_frequency:.2f} Hz",
                    f"RPM: {self.actual_rpm:.0f}",
                    f"Current: {self.actual_current:.2f} A",
                    f"Voltage: {self.actual_voltage:.1f} V",
                    f"Fault: {self.fault}",
                    f"Fault Code: {self.fault_code}",
                )
            )

        driver = self.get_driver()

        if driver is None:
            return "ERROR: VFD driver unavailable."

        if operation == "get":
            if len(parts) != 2:
                return "ERROR: Use: get PDxxx"

            parameter = parts[1].upper()

            if not self._valid_parameter_name(parameter):
                return "ERROR: Parameter must be PD000-PD999."

            method = getattr(
                driver,
                "get_parameter",
                None,
            )

            if method is None:
                return (
                    "ERROR: Driver does not support "
                    "get_parameter()."
                )

            try:
                value = method(
                    self._parameter_number(parameter)
                )

                if value is None:
                    return (
                        f"ERROR reading {parameter}: "
                        f"{getattr(driver, 'last_error', '')}"
                    )

                return f"{parameter} = {value}"

            except Exception as exc:
                return (
                    f"ERROR reading {parameter}: "
                    f"{exc}"
                )

        if operation == "set":
            if len(parts) != 3:
                return "ERROR: Use: set PDxxx VALUE"

            parameter = parts[1].upper()

            if not self._valid_parameter_name(parameter):
                return "ERROR: Parameter must be PD000-PD999."

            if not self.enabled:
                return "ERROR: VFD node is disabled."

            if not self.armed:
                return "ERROR: VFD is not ARMED."

            try:
                value = int(float(parts[2]))
            except ValueError:
                return (
                    f"ERROR: Invalid value: {parts[2]}"
                )

            method = getattr(
                driver,
                "set_parameter",
                None,
            )

            if method is None:
                return (
                    "ERROR: Driver does not support "
                    "set_parameter()."
                )

            try:
                result = bool(
                    method(
                        self._parameter_number(parameter),
                        value,
                    )
                )

                if result:
                    return (
                        f"OK: {parameter} = {value}"
                    )

                return (
                    f"ERROR writing {parameter}: "
                    f"{getattr(driver, 'last_error', '')}"
                )

            except Exception as exc:
                return (
                    f"ERROR writing {parameter}: "
                    f"{exc}"
                )

        if operation == "start":
            if not self.enabled:
                return "ERROR: VFD node is disabled."

            if not self.armed:
                return "ERROR: VFD is not ARMED."

            if not self.connected and not self.connect():
                return f"ERROR: {self.status_text}"

            method = getattr(
                driver,
                "start",
                None,
            )

            if method is None:
                return "ERROR: Driver does not support start()."

            try:
                if method():
                    self.running = True
                    return "OK: START"

                return (
                    f"ERROR: START failed: "
                    f"{getattr(driver, 'last_error', '')}"
                )

            except Exception as exc:
                return f"ERROR: {exc}"

        if operation in {"stop", "halt"}:
            if not self.connected:
                return "ERROR: VFD is not connected."

            result = self._apply_stop(driver)

            if result:
                return "OK: STOP"

            return (
                f"ERROR: STOP failed: "
                f"{getattr(driver, 'last_error', '')}"
            )

        if operation in {"freq", "frequency"}:
            if len(parts) != 2:
                return "ERROR: Use: freq VALUE"

            if not self.enabled:
                return "ERROR: VFD node is disabled."

            if not self.armed:
                return "ERROR: VFD is not ARMED."

            try:
                frequency = float(parts[1])
            except ValueError:
                return (
                    f"ERROR: Invalid frequency: "
                    f"{parts[1]}"
                )

            frequency = self.clamp_frequency(
                frequency
            )

            if not self.connected and not self.connect():
                return f"ERROR: {self.status_text}"

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

            try:
                if method(frequency):
                    self.frequency_command = frequency
                    self.speed_command = (
                        self.frequency_to_rpm(
                            frequency
                        )
                    )

                    return (
                        f"OK: FREQUENCY "
                        f"{frequency:g} Hz"
                    )

                return (
                    f"ERROR: Frequency command failed: "
                    f"{getattr(driver, 'last_error', '')}"
                )

            except Exception as exc:
                return f"ERROR: {exc}"

        if operation == "reset":
            if not self.enabled:
                return "ERROR: VFD node is disabled."

            if not self.armed:
                return "ERROR: VFD is not ARMED."

            if not self.connected and not self.connect():
                return f"ERROR: {self.status_text}"

            method = getattr(
                driver,
                "reset_fault",
                None,
            )

            if method is None:
                return (
                    "ERROR: Driver does not support "
                    "reset_fault()."
                )

            try:
                if method():
                    return "OK: RESET"

                return (
                    f"ERROR: RESET failed: "
                    f"{getattr(driver, 'last_error', '')}"
                )

            except Exception as exc:
                return f"ERROR: {exc}"

        return f"ERROR: Unknown command: {command}"

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="VFD", icon="DRIVER")
        box.prop(self, "device_name", text="Name")
        box.label(text=f"Driver: {self.driver_name}")

        box = layout.box()
        box.label(text="Connection", icon="LINKED")
        box.prop(self, "serial_port", text="Port")
        box.prop(self, "baudrate", text="Baud")
        box.prop(self, "slave_id", text="Address")

        row = box.row(align=True)

        op = row.operator(
            "vfd.node_connect",
            text="Connect",
            icon="LINKED",
        )
        op.node_name = self.name

        op = row.operator(
            "vfd.node_disconnect",
            text="Disconnect",
            icon="UNLINKED",
        )
        op.node_name = self.name

        box = layout.box()
        box.label(text="Motor", icon="MESH_CIRCLE")
        box.prop(self, "motor_power_kw", text="Power")
        box.prop(self, "motor_voltage", text="Voltage")
        box.prop(self, "motor_frequency", text="Rated Hz")
        box.prop(self, "motor_rpm", text="Rated RPM")

        box = layout.box()
        box.label(text="Frequency Limits")
        box.prop(self, "minimum_frequency", text="Min")
        box.prop(self, "maximum_frequency", text="Max")

        box = layout.box()
        box.label(text="Command", icon="PLAY")
        box.prop(self, "frequency_command", text="Frequency")
        box.label(
            text=(
                f"RPM: "
                f"{self.frequency_to_rpm(self.frequency_command):.0f}"
            )
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

        box = layout.box()
        box.label(
            text="VFD Console",
            icon="CONSOLE",
        )
        box.prop(
            self,
            "console_command",
            text="",
        )

        row = box.row()
        row.scale_y = 1.3

        op = row.operator(
            "vfd.console_execute",
            text="EXECUTE",
            icon="PLAY",
        )
        op.node_name = self.name

        box.label(
            text=self.console_output,
            icon="INFO",
        )

        help_box = box.box()
        help_box.label(text="Examples:")
        help_box.label(text="connect")
        help_box.label(text="status")
        help_box.label(text="get PD142")
        help_box.label(text="set PD142 60")
        help_box.label(text="freq 200")
        help_box.label(text="start")
        help_box.label(text="stop")
        help_box.label(text="reset")

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
        row.alert = self.armed
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

        box = layout.box()
        box.label(
            text="Status",
            icon="INFO",
        )
        box.label(text=self.status_text)
        box.label(
            text=(
                f"Frequency: "
                f"{self.actual_frequency:.1f} Hz"
            )
        )
        box.label(
            text=(
                f"RPM: "
                f"{self.actual_rpm:.0f}"
            )
        )
        box.label(
            text=(
                f"Current: "
                f"{self.actual_current:.2f} A"
            )
        )
        box.label(
            text=(
                f"Voltage: "
                f"{self.actual_voltage:.1f} V"
            )
        )

        if self.fault:
            row = box.row()
            row.alert = True
            row.label(
                text=f"FAULT: {self.fault_code}",
                icon="ERROR",
            )

    def draw_label(self):
        return f"VFD {self.device_name}"


def _find_node(node_name):
    for node_group in bpy.data.node_groups:
        node = node_group.nodes.get(node_name)
        if node is not None:
            return node
    return None


class VFD_OT_connect(bpy.types.Operator):
    bl_idname = "vfd.node_connect"
    bl_label = "Connect VFD"

    node_name: StringProperty()

    def execute(self, context):
        node = _find_node(self.node_name)

        if node is None:
            self.report({"ERROR"}, "VFD node not found")
            return {"CANCELLED"}

        if node.connect():
            node.update_status()
            return {"FINISHED"}

        self.report(
            {"ERROR"},
            node.status_text,
        )
        return {"CANCELLED"}


class VFD_OT_disconnect(bpy.types.Operator):
    bl_idname = "vfd.node_disconnect"
    bl_label = "Disconnect VFD"

    node_name: StringProperty()

    def execute(self, context):
        node = _find_node(self.node_name)

        if node is None:
            self.report({"ERROR"}, "VFD node not found")
            return {"CANCELLED"}

        node.disconnect()
        return {"FINISHED"}


classes = (
    VFDValueSocket,
    VFDStatusSocket,
    VFD_OT_console_execute,
    VFD_OT_connect,
    VFD_OT_disconnect,
    VFDNode,
)
