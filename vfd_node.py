from __future__ import annotations
import bpy
from bpy.types import Node, NodeSocket
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
try:
    from .vfd_manager import VFDManager, VFDMotorConfig, VFDDirection
except ImportError:
    from vfd_manager import VFDManager, VFDMotorConfig, VFDDirection
_MANAGERS = {}
def get_vfd_manager(node):
    if node is None:
        return None
    return _MANAGERS.get(id(node))
def create_vfd_manager(node):
    manager = get_vfd_manager(node)
    if manager is not None:
        return manager
    motor = VFDMotorConfig(
        power_kw=node.motor_power_kw,
        voltage_v=node.motor_voltage,
        rated_frequency_hz=node.motor_frequency,
        rated_rpm=node.motor_rpm,
        min_frequency_hz=node.minimum_frequency,
        max_frequency_hz=node.maximum_frequency,
        min_rpm=node.minimum_rpm,
        max_rpm=node.maximum_rpm,
    )
    manager = VFDManager(motor=motor)
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
class VFDValueSocket(NodeSocket):
    bl_idname = "VFDValueSocket"
    bl_label = "VFD Value"
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
def find_node(name):
    for tree in bpy.data.node_groups:
        node = tree.nodes.get(name)
        if node is not None:
            return node
    return None
class VFDNode(Node):
    bl_idname = "VFDNode"
    bl_label = "VFD"
    bl_icon = "DRIVER"
    enabled: BoolProperty(name="Enabled", default=True)
    armed: BoolProperty(name="ARM", default=False)
    device_name: StringProperty(name="Device", default="HY01D523B")
    serial_port: StringProperty(name="RS-485 Port", default="COM3")
    slave_id: IntProperty(name="Slave ID", default=4, min=1, max=247)
    baudrate: IntProperty(name="Baud Rate", default=9600, min=1200, max=115200)
    motor_power_kw: FloatProperty(name="Motor Power", default=1.5, min=0.0)
    motor_voltage: FloatProperty(name="Motor Voltage", default=220.0, min=0.0)
    motor_frequency: FloatProperty(name="Rated Frequency", default=400.0, min=1.0)
    motor_rpm: FloatProperty(name="Rated RPM", default=24000.0, min=1.0)
    minimum_frequency: FloatProperty(name="Minimum Frequency", default=0.0, min=0.0)
    maximum_frequency: FloatProperty(name="Maximum Frequency", default=400.0, min=0.0)
    minimum_rpm: FloatProperty(name="Minimum RPM", default=0.0, min=0.0)
    maximum_rpm: FloatProperty(name="Maximum RPM", default=24000.0, min=0.0)
    frequency_command: FloatProperty(name="Frequency", default=0.0, min=0.0)
    rpm_command: FloatProperty(name="RPM", default=0.0, min=0.0)
    running_command: BoolProperty(name="RUN", default=False)
    reverse_command: BoolProperty(name="REVERSE", default=False)
    reset_command: BoolProperty(name="RESET", default=False)
    connected: BoolProperty(name="Connected", default=False)
    running: BoolProperty(name="Running", default=False)
    fault: BoolProperty(name="Fault", default=False)
    fault_code: IntProperty(name="Fault Code", default=0)
    actual_frequency: FloatProperty(name="Actual Frequency", default=0.0)
    actual_rpm: FloatProperty(name="Actual RPM", default=0.0)
    actual_current: FloatProperty(name="Current", default=0.0)
    actual_voltage: FloatProperty(name="Voltage", default=0.0)
    actual_power: FloatProperty(name="Power", default=0.0)
    status_text: StringProperty(name="Status", default="Disconnected")
    console_command: StringProperty(name="Command", default="status")
    console_output: StringProperty(name="Output", default="Ready")
    def init(self, context):
        self.inputs.new("VFDValueSocket", "Frequency")
        self.inputs.new("VFDValueSocket", "RPM")
        self.inputs.new("NodeSocketBool", "RUN")
        self.inputs.new("NodeSocketBool", "REVERSE")
        self.inputs.new("NodeSocketBool", "RESET")
        self.outputs.new("VFDValueSocket", "Frequency")
        self.outputs.new("VFDValueSocket", "RPM")
        self.outputs.new("VFDValueSocket", "Current")
        self.outputs.new("VFDValueSocket", "Voltage")
        self.outputs.new("VFDValueSocket", "Power")
        self.outputs.new("VFDStatusSocket", "Connected")
        self.outputs.new("VFDStatusSocket", "Running")
        self.outputs.new("VFDStatusSocket", "Fault")
        self.outputs.new("VFDStatusSocket", "Fault Code")
    def free(self):
        remove_vfd_manager(self)
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
            voltage_v=self.motor_voltage_v,
            rated_frequency_hz=self.rated_frequency_hz,
            rated_rpm=self.rated_rpm,
            rated_current_a=self.rated_current_a,
            poles=self.motor_poles,
            min_frequency_hz=self.min_frequency_hz,
            max_frequency_hz=self.max_frequency_hz,
            min_rpm=self.min_rpm,
            max_rpm=self.max_rpm,
        )
        manager.set_enabled(self.enabled)
        manager.set_armed(self.armed)
    def connect_vfd(self):
        self.update_manager_config()
        result = self.get_manager().connect()
        self.update_status()
    return result

    def disconnect_vfd(self):
        manager = self.get_manager()
        manager.disconnect()
        self.update_status()
    def _socket_float(self, name, default):
        socket = self.inputs.get(name)
        if socket is None:
            return default
        if socket.is_linked:
            source = socket.links[0].from_socket
            if hasattr(source, "default_value"):
                try:
                    return float(source.default_value)
                except Exception:
                    pass
        try:
            return float(socket.default_value)
        except Exception:
            return default
    def _socket_bool(self, name, default):
        socket = self.inputs.get(name)
        if socket is None:
            return default
        if socket.is_linked:
            source = socket.links[0].from_socket
            if hasattr(source, "default_value"):
                try:
                    return bool(source.default_value)
                except Exception:
                    pass
        try:
            return bool(socket.default_value)
        except Exception:
            return default
    def get_command(self):
        frequency = self.frequency_command
        rpm = self.rpm_command
        rpm_socket = self.inputs.get("RPM")
        frequency_socket = self.inputs.get("Frequency")
        if rpm_socket is not None and rpm_socket.is_linked:
            rpm = self._socket_float("RPM", rpm)
            frequency = self.rpm_to_frequency(rpm)
        elif frequency_socket is not None and frequency_socket.is_linked:
            frequency = self._socket_float("Frequency", frequency)
            rpm = self.frequency_to_rpm(frequency)
        run = self._socket_bool("RUN", self.running_command)
        reverse = self._socket_bool("REVERSE", self.reverse_command)
        reset = self._socket_bool("RESET", self.reset_command)
        if not self.enabled or not self.armed:
            run = False
        return {"run": run, "frequency": frequency, "rpm": rpm, "reverse": reverse, "reset": reset}
    def apply_command(self):
        manager = self.get_manager()
        self.update_manager_config()
        command = self.get_command()
        if not manager.is_connected():
            self.status_text = "Disconnected"
            return False
        result = manager.apply_command(
            run=command["run"],
            frequency_hz=command["frequency"],
            reverse=command["reverse"],
            reset=command["reset"],
        )
        self.update_status()
        return result
    def update_status(self):
        manager = self.get_manager()
        status = manager.get_status()
        self.connected = bool(status.connected)
        self.running = bool(status.running)
        self.fault = bool(status.fault)
        self.fault_code = int(status.fault_code)
        self.actual_frequency = float(status.frequency_hz)
        self.actual_rpm = float(status.rpm)
        self.actual_current = float(status.current_a)
        self.actual_voltage = float(status.voltage_v)
        self.actual_power = float(status.power_kw)
        self.status_text = str(status.fault_text or status.state.value)
        self.outputs["Frequency"].default_value = self.actual_frequency
        self.outputs["RPM"].default_value = self.actual_rpm
        self.outputs["Current"].default_value = self.actual_current
        self.outputs["Voltage"].default_value = self.actual_voltage
        self.outputs["Power"].default_value = self.actual_power
        self.outputs["Connected"].default_value = self.connected
        self.outputs["Running"].default_value = self.running
        self.outputs["Fault"].default_value = self.fault
        self.outputs["Fault Code"].default_value = self.fault_code
    def frequency_to_rpm(self, frequency):
        if self.motor_frequency <= 0.0:
            return 0.0
        return float(frequency) / self.motor_frequency * self.motor_rpm
    def rpm_to_frequency(self, rpm):
        if self.motor_rpm <= 0.0:
            return 0.0
        return float(rpm) / self.motor_rpm * self.motor_frequency
    def execute_command(self, command):
        manager = self.get_manager()
        text = command.strip()
        if not text:
            return "ERROR: Empty command."
        parts = text.split()
        operation = parts[0].lower()
        if operation == "connect":
            return "OK: Connected" if self.connect_vfd() else f"ERROR: {manager.status.fault_text}"
        if operation == "disconnect":
            self.disconnect_vfd()
            return "OK: Disconnected"
        if operation == "status":
            self.update_status()
            return f"Connected: {self.connected}\nRunning: {self.running}\nFrequency: {self.actual_frequency:.2f} Hz\nRPM: {self.actual_rpm:.0f}\nCurrent: {self.actual_current:.2f} A\nVoltage: {self.actual_voltage:.1f} V\nPower: {self.actual_power:.2f} kW\nFault: {self.fault}\nFault code: {self.fault_code}"
        if operation in {"get", "read"}:
        if len(parts) != 2:
            return "ERROR: Use: get PD163"
        parameter_text = parts[1].upper()
        if parameter_text.startswith("PD"):
            parameter_text = parameter_text[2:]
        try:
            parameter = int(parameter_text)
        except ValueError:
            return "ERROR: Invalid parameter. Use PD000-PD182."
        if parameter < 0 or parameter > 182:
            return "ERROR: Parameter must be PD000-PD182."
        if not manager.is_connected():
            return "ERROR: VFD is disconnected."
        value = manager.read_parameter(parameter)
        if value is None:
            return f"ERROR: {manager.status.fault_text}"
        return f"OK: PD{parameter:03d} = {value}"
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
            return "ERROR: Invalid parameter or value."
        if parameter < 0 or parameter > 182:
            return "ERROR: Parameter must be PD000-PD182."
        if value < 0 or value > 65535:
            return "ERROR: Value must be 0-65535."
        if not manager.is_connected():
            return "ERROR: VFD is disconnected."
        if not manager.write_parameter(parameter, value):
            return f"ERROR: {manager.status.fault_text}"
            return f"OK: PD{parameter:03d} = {value}"
        if operation in {"start", "run"}:
            if not self.enabled or not self.armed:
                return "ERROR: VFD is not enabled and armed."
            if not manager.is_connected():
                return "ERROR: VFD is disconnected."
            return "OK: Started" if manager.start() else f"ERROR: {manager.status.fault_text}"
        if operation in {"stop", "halt"}:
            return "OK: Stopped" if manager.stop() else f"ERROR: {manager.status.fault_text}"
        if operation in {"freq", "frequency"}:
            if len(parts) != 2:
                return "ERROR: Use: freq 200"
            try:
                frequency = float(parts[1])
            except ValueError:
                return "ERROR: Invalid frequency."
            return "OK: Frequency set" if manager.set_frequency(frequency) else f"ERROR: {manager.status.fault_text}"
        if operation == "reset":
            return "OK: Fault reset" if manager.reset_fault() else f"ERROR: {manager.status.fault_text}"
        return f"ERROR: Unknown command: {operation}"
    def draw_buttons(self, context, layout):
        layout.label(text="HY01D523B VFD", icon="DRIVER")
        box = layout.box()
        box.label(text="Connection")
        box.prop(self, "serial_port", text="RS-485")
        box.prop(self, "slave_id", text="Address")
        box.prop(self, "baudrate", text="Baud")
        row = box.row(align=True)
        op = row.operator("vfd.connect", text="Connect", icon="LINKED")
        op.node_name = self.name
        op = row.operator("vfd.disconnect", text="Disconnect", icon="UNLINKED")
        op.node_name = self.name
        box = layout.box()
        box.label(text="Motor")
        box.prop(self, "motor_power_kw", text="Power kW")
        box.prop(self, "motor_voltage", text="Voltage")
        box.prop(self, "motor_frequency", text="Rated Hz")
        box.prop(self, "motor_rpm", text="Rated RPM")
        box.prop(self, "minimum_frequency", text="Min Hz")
        box.prop(self, "maximum_frequency", text="Max Hz")
        box = layout.box()
        box.label(text="Control")
        box.prop(self, "frequency_command", text="Frequency")
        box.prop(self, "rpm_command", text="RPM")
        box.prop(self, "running_command", text="RUN", toggle=True)
        box.prop(self, "reverse_command", text="REVERSE", toggle=True)
        box.prop(self, "reset_command", text="RESET", toggle=True)
        box = layout.box()
        box.prop(self, "enabled", text="Enabled")
        box.prop(self, "armed", text="ARM")
        box = layout.box()
        box.label(text="Status")
        box.label(text=self.status_text)
        box.label(text=f"{self.actual_frequency:.1f} Hz / {self.actual_rpm:.0f} RPM")
        box.label(text=f"{self.actual_current:.2f} A / {self.actual_voltage:.1f} V")
        if self.fault:
            box.label(text=f"FAULT {self.fault_code}", icon="ERROR")
        box = layout.box()
        box.label(text="Console")
        box.prop(self, "console_command", text="")
        op = box.operator("vfd.execute", text="Execute", icon="PLAY")
        op.node_name = self.name
        op.command = self.console_command
        box.label(text=self.console_output)
    def draw_label(self):
        return self.device_name
classes = (VFDValueSocket, VFDStatusSocket, VFD_OT_connect, VFD_OT_disconnect, VFD_OT_execute, VFDNode)
