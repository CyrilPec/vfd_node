bl_info = {
    "name": "VFD Geometry Node",
    "author": "CyrilPec / modified",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "Geometry Nodes > Add > VFD",
    "description": "Geometry Nodes interface for controlling a HY01D523B VFD",
    "category": "Node",
}

import bpy
import time
import threading

from bpy.types import Node, NodeSocket, Operator
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)


# ============================================================================
# GLOBAL VFD STATE
# ============================================================================

_VFD_CONNECTION = None
_VFD_LOCK = threading.Lock()

VFD_CONNECTED = False
VFD_LAST_ERROR = ""
VFD_LAST_UPDATE = 0.0


# ============================================================================
# OPTIONAL MODBUS IMPORT
# ============================================================================

try:
    from pymodbus.client.sync import ModbusSerialClient
except ImportError:
    ModbusSerialClient = None


# ============================================================================
# VFD COMMUNICATION
# ============================================================================

class VFDController:
    """
    Small HY01D523B controller wrapper.

    Communication is deliberately kept outside the Blender node so the
    Geometry Node remains lightweight.
    """

    def __init__(self):
        self.client = None
        self.connected = False

        self.port = "COM3"
        self.slave_id = 4
        self.baudrate = 9600

        self.last_error = ""

        self.last_frequency = 0.0
        self.last_running = False
        self.last_reverse = False

    # ------------------------------------------------------------------
    # CONNECT
    # ------------------------------------------------------------------

    def connect(self, port, slave_id, baudrate):

        global VFD_CONNECTED
        global VFD_LAST_ERROR

        self.disconnect()

        self.port = port
        self.slave_id = int(slave_id)
        self.baudrate = int(baudrate)

        if ModbusSerialClient is None:
            self.last_error = (
                "pymodbus is not installed. "
                "Install pymodbus in Blender's Python."
            )

            VFD_LAST_ERROR = self.last_error
            VFD_CONNECTED = False
            return False

        try:

            self.client = ModbusSerialClient(
                method="rtu",
                port=self.port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=0.2,
            )

            self.connected = bool(self.client.connect())

            if not self.connected:
                self.last_error = (
                    "Could not connect to VFD on {}".format(
                        self.port
                    )
                )

                VFD_LAST_ERROR = self.last_error
                VFD_CONNECTED = False

                return False

            VFD_CONNECTED = True
            VFD_LAST_ERROR = ""

            return True

        except Exception as exc:

            self.connected = False

            self.last_error = str(exc)

            VFD_LAST_ERROR = self.last_error
            VFD_CONNECTED = False

            return False

    # ------------------------------------------------------------------
    # DISCONNECT
    # ------------------------------------------------------------------

    def disconnect(self):

        global VFD_CONNECTED

        try:
            if self.client is not None:
                self.client.close()
        except Exception:
            pass

        self.client = None
        self.connected = False

        VFD_CONNECTED = False

    # ------------------------------------------------------------------
    # WRITE REGISTER
    # ------------------------------------------------------------------

    def write_register(self, address, value):

        if not self.connected or self.client is None:
            return False

        try:

            result = self.client.write_register(
                address,
                int(value),
                slave=self.slave_id,
            )

            if hasattr(result, "isError") and result.isError():
                return False

            return True

        except Exception as exc:

            self.last_error = str(exc)

            global VFD_LAST_ERROR
            VFD_LAST_ERROR = self.last_error

            return False

    # ------------------------------------------------------------------
    # READ REGISTER
    # ------------------------------------------------------------------

    def read_register(self, address):

        if not self.connected or self.client is None:
            return None

        try:

            result = self.client.read_holding_registers(
                address,
                1,
                slave=self.slave_id,
            )

            if result is None:
                return None

            if hasattr(result, "isError") and result.isError():
                return None

            if not result.registers:
                return None

            return result.registers[0]

        except Exception as exc:

            self.last_error = str(exc)

            global VFD_LAST_ERROR
            VFD_LAST_ERROR = self.last_error

            return None

    # ------------------------------------------------------------------
    # FREQUENCY
    # ------------------------------------------------------------------

    def set_frequency(self, frequency):

        """
        HY01D523B frequency command.

        Default scaling used here:
            400.0 Hz -> 4000

        If your VFD uses another scaling, change this value.
        """

        value = int(round(float(frequency) * 10.0))

        return self.write_register(
            0x1000,
            value,
        )

    # ------------------------------------------------------------------
    # RUN / STOP
    # ------------------------------------------------------------------

    def set_run(self, run):

        """
        HY01D523B run command.

        Forward:
            1

        Stop:
            0
        """

        if run:
            value = 1
        else:
            value = 0

        return self.write_register(
            0x1001,
            value,
        )

    # ------------------------------------------------------------------
    # DIRECTION
    # ------------------------------------------------------------------

    def set_reverse(self, reverse):

        """
        Direction command.

        Forward:
            0

        Reverse:
            2
        """

        if reverse:
            value = 2
        else:
            value = 0

        return self.write_register(
            0x1001,
            value,
        )

    # ------------------------------------------------------------------
    # RESET
    # ------------------------------------------------------------------

    def reset(self):

        return self.write_register(
            0x1001,
            6,
        )


# ============================================================================
# GLOBAL CONTROLLER
# ============================================================================

_CONTROLLER = VFDController()


def get_controller():
    return _CONTROLLER


# ============================================================================
# NODE SOCKET
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

        layout.label(text=text)

    def draw_color(
        self,
        context,
        node,
    ):

        return (
            0.15,
            0.65,
            0.25,
            1.0,
        )


# ============================================================================
# CONNECT OPERATOR
# ============================================================================

class VFD_OT_connect(Operator):

    bl_idname = "vfd.connect"
    bl_label = "Connect VFD"

    node_name: StringProperty()

    def execute(self, context):

        node = find_node(self.node_name)

        if node is None:

            self.report(
                {"ERROR"},
                "VFD node not found",
            )

            return {"CANCELLED"}

        if node.connect_vfd():

            self.report(
                {"INFO"},
                "VFD connected",
            )

            return {"FINISHED"}

        self.report(
            {"ERROR"},
            node.status_text,
        )

        return {"CANCELLED"}


# ============================================================================
# DISCONNECT OPERATOR
# ============================================================================

class VFD_OT_disconnect(Operator):

    bl_idname = "vfd.disconnect"
    bl_label = "Disconnect VFD"

    node_name: StringProperty()

    def execute(self, context):

        node = find_node(self.node_name)

        if node is None:
            return {"CANCELLED"}

        node.disconnect_vfd()

        return {"FINISHED"}


# ============================================================================
# RESET OPERATOR
# ============================================================================

class VFD_OT_reset(Operator):

    bl_idname = "vfd.reset"
    bl_label = "Reset VFD"

    node_name: StringProperty()

    def execute(self, context):

        node = find_node(self.node_name)

        if node is None:
            return {"CANCELLED"}

        if node.reset_vfd():

            self.report(
                {"INFO"},
                "VFD reset",
            )

            return {"FINISHED"}

        self.report(
            {"ERROR"},
            node.status_text,
        )

        return {"CANCELLED"}


# ============================================================================
# VFD NODE
# ============================================================================

class VFDNode(Node):

    bl_idname = "VFDNode"
    bl_label = "VFD"
    bl_icon = "DRIVER"

    # ------------------------------------------------------------------
    # CONNECTION
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
    # SAFETY
    # ------------------------------------------------------------------

    enabled: BoolProperty(
        name="Enabled",
        description="Enable VFD control",
        default=True,
    )

    armed: BoolProperty(
        name="ARM",
        description="Allow commands to be sent to the VFD",
        default=False,
    )

    # ------------------------------------------------------------------
    # MOTOR
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

    # ------------------------------------------------------------------
    # LIMITS
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # COMMAND
    # ------------------------------------------------------------------

    frequency_command: FloatProperty(
        name="Frequency",
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

    # ------------------------------------------------------------------
    # STATUS
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

    status_text: StringProperty(
        name="Status",
        default="Disconnected",
    )

    last_command: FloatProperty(
        name="Last Command",
        default=0.0,
    )

    # ------------------------------------------------------------------
    # NODE POLL
    # ------------------------------------------------------------------

    @classmethod
    def poll(cls, ntree):

        return ntree.bl_idname == "GeometryNodeTree"

    # ------------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------------

    def init(self, context):

        frequency = self.inputs.new(
            "NodeSocketFloat",
            "Frequency",
        )

        frequency.default_value = 0.0
        frequency.min_value = 0.0
        frequency.max_value = 400.0

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

        self.outputs.new(
            "VFDValueSocket",
            "Frequency",
        )

        self.outputs.new(
            "NodeSocketBool",
            "Running",
        )

        self.outputs.new(
            "NodeSocketBool",
            "Connected",
        )

        self.outputs.new(
            "NodeSocketBool",
            "Fault",
        )

        self.outputs.new(
            "NodeSocketFloat",
            "RPM",
        )

    # ------------------------------------------------------------------
    # COPY
    # ------------------------------------------------------------------

    def copy(self, node):

        self.connected = False
        self.status_text = "Disconnected"

    # ------------------------------------------------------------------
    # FREE
    # ------------------------------------------------------------------

    def free(self):

        # Do not automatically stop another node when Blender
        # deletes this node.
        pass

    # ------------------------------------------------------------------
    # CONNECT
    # ------------------------------------------------------------------

    def connect_vfd(self):

        controller = get_controller()

        with _VFD_LOCK:

            result = controller.connect(
                self.serial_port,
                self.slave_id,
                self.baudrate,
            )

        self.connected = result

        if result:

            self.status_text = (
                "Connected: {}".format(
                    self.serial_port
                )
            )

        else:

            self.status_text = (
                controller.last_error
                or "Connection failed"
            )

        return result

    # ------------------------------------------------------------------
    # DISCONNECT
    # ------------------------------------------------------------------

    def disconnect_vfd(self):

        controller = get_controller()

        with _VFD_LOCK:
            controller.disconnect()

        self.connected = False
        self.status_text = "Disconnected"

    # ------------------------------------------------------------------
    # RESET
    # ------------------------------------------------------------------

    def reset_vfd(self):

        controller = get_controller()

        if not controller.connected:

            self.status_text = "Not connected"
            return False

        with _VFD_LOCK:
            result = controller.reset()

        if result:

            self.status_text = "Reset command sent"

        else:

            self.status_text = (
                controller.last_error
                or "Reset failed"
            )

        return result

    # ------------------------------------------------------------------
    # GET FREQUENCY INPUT
    # ------------------------------------------------------------------

    def get_frequency_input(self):

        socket = self.inputs.get("Frequency")

        if socket is None:
            return self.frequency_command

        try:

            if socket.is_linked:

                value = socket.links[0].from_socket

                if hasattr(value, "default_value"):

                    return float(
                        value.default_value
                    )

            return float(
                socket.default_value
            )

        except Exception:

            return float(
                self.frequency_command
            )

    # ------------------------------------------------------------------
    # GET RUN INPUT
    # ------------------------------------------------------------------

    def get_run_input(self):

        socket = self.inputs.get("RUN")

        if socket is None:
            return self.running_command

        try:

            if socket.is_linked:

                value = socket.links[0].from_socket

                if hasattr(value, "default_value"):

                    return bool(
                        value.default_value
                    )

            return bool(
                socket.default_value
            )

        except Exception:

            return bool(
                self.running_command
            )

    # ------------------------------------------------------------------
    # GET REVERSE INPUT
    # ------------------------------------------------------------------

    def get_reverse_input(self):

        socket = self.inputs.get("REVERSE")

        if socket is None:
            return self.reverse_command

        try:

            if socket.is_linked:

                value = socket.links[0].from_socket

                if hasattr(value, "default_value"):

                    return bool(
                        value.default_value
                    )

            return bool(
                socket.default_value
            )

        except Exception:

            return bool(
                self.reverse_command
            )

    # ------------------------------------------------------------------
    # CALCULATE FREQUENCY
    # ------------------------------------------------------------------

    def calculate_frequency(self):

        frequency = self.get_frequency_input()

        low = min(
            self.minimum_frequency,
            self.maximum_frequency,
        )

        high = max(
            self.minimum_frequency,
            self.maximum_frequency,
        )

        frequency = max(
            low,
            min(
                frequency,
                high,
            ),
        )

        return float(frequency)

    # ------------------------------------------------------------------
    # SEND COMMAND
    # ------------------------------------------------------------------

    def update_command(self):

        if not self.enabled:
            return

        if not self.armed:
            return

        controller = get_controller()

        if not controller.connected:

            self.connected = False
            self.status_text = "Not connected"

            return

        frequency = self.calculate_frequency()
        running = self.get_run_input()
        reverse = self.get_reverse_input()

        # ----------------------------------------------------------
        # FREQUENCY
        # ----------------------------------------------------------

        with _VFD_LOCK:

            if not controller.set_frequency(
                frequency
            ):

                self.status_text = (
                    controller.last_error
                    or "Frequency command failed"
                )

                return

            # ------------------------------------------------------
            # DIRECTION
            # ------------------------------------------------------

            if not controller.set_reverse(
                reverse
            ):

                self.status_text = (
                    controller.last_error
                    or "Direction command failed"
                )

                return

            # ------------------------------------------------------
            # RUN
            # ------------------------------------------------------

            if not controller.set_run(
                running
            ):

                self.status_text = (
                    controller.last_error
                    or "RUN command failed"
                )

                return

        self.last_command = frequency
        self.running = running
        self.reverse = reverse
        self.connected = True

        self.status_text = "Command OK"

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(self):

        try:

            frequency = self.calculate_frequency()

            self.last_command = frequency

            if self.id_data:
                self.id_data.update_tag()

        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def draw_buttons(self, context, layout):

        # ==========================================================
        # CONNECTION
        # ==========================================================

        box = layout.box()

        box.label(
            text="CONNECTION",
            icon="LINKED",
        )

        box.prop(
            self,
            "serial_port",
        )

        box.prop(
            self,
            "slave_id",
        )

        box.prop(
            self,
            "baudrate",
        )

        row = box.row(align=True)

        if self.connected:

            op = row.operator(
                "vfd.disconnect",
                text="Disconnect",
                icon="UNLINKED",
            )

            op.node_name = self.name

        else:

            op = row.operator(
                "vfd.connect",
                text="Connect",
                icon="LINKED",
            )

            op.node_name = self.name

        # ==========================================================
        # SAFETY
        # ==========================================================

        box = layout.box()

        box.label(
            text="SAFETY",
            icon="LOCKED",
        )

        box.prop(
            self,
            "enabled",
        )

        row = box.row()

        row.prop(
            self,
            "armed",
            toggle=True,
        )

        # ==========================================================
        # MOTOR
        # ==========================================================

        box = layout.box()

        box.label(
            text="MOTOR",
            icon="MOD_PHYSICS",
        )

        box.prop(
            self,
            "motor_power_kw",
        )

        box.prop(
            self,
            "motor_voltage",
        )

        box.prop(
            self,
            "motor_frequency",
        )

        box.prop(
            self,
            "motor_rpm",
        )

        # ==========================================================
        # LIMITS
        # ==========================================================

        box = layout.box()

        box.label(
            text="LIMITS",
            icon="DRIVER_DISTANCE",
        )

        box.prop(
            self,
            "minimum_frequency",
        )

        box.prop(
            self,
            "maximum_frequency",
        )

        # ==========================================================
        # MANUAL COMMAND
        # ==========================================================

        box = layout.box()

        box.label(
            text="MANUAL COMMAND",
            icon="PLAY",
        )

        box.prop(
            self,
            "frequency_command",
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

        op = row.operator(
            "vfd.reset",
            text="RESET",
            icon="FILE_REFRESH",
        )

        op.node_name = self.name

        # ==========================================================
        # STATUS
        # ==========================================================

        box = layout.box()

        box.label(
            text="STATUS",
            icon="INFO",
        )

        if self.connected:

            box.label(
                text="CONNECTED",
                icon="CHECKMARK",
            )

        else:

            box.label(
                text="DISCONNECTED",
                icon="X",
            )

        box.label(
            text=self.status_text,
        )

        box.separator()

        box.label(
            text="Command: {:.1f} Hz".format(
                self.last_command
            )
        )

        box.label(
            text="Running: {}".format(
                "YES"
                if self.running
                else "NO"
            )
        )

        box.label(
            text="Reverse: {}".format(
                "YES"
                if self.reverse
                else "NO"
            )
        )

        if self.fault:

            box.label(
                text="FAULT {}".format(
                    self.fault_code
                ),
                icon="ERROR",
            )


# ============================================================================
# FIND NODE
# ============================================================================

def find_node(node_name):

    for tree in bpy.data.node_groups:

        for node in tree.nodes:

            if node.name == node_name:

                return node

    return None


# ============================================================================
# NODE MENU
# ============================================================================

def vfd_node_menu(self, context):

    self.layout.operator(
        "node.add_node",
        text="VFD",
        icon="DRIVER",
    ).type = "VFDNode"


# ============================================================================
# TIMER
# ============================================================================

_TIMER_RUNNING = False


def vfd_timer():

    global _TIMER_RUNNING

    if not _TIMER_RUNNING:
        return None

    try:

        for tree in bpy.data.node_groups:

            if tree.bl_idname != "GeometryNodeTree":
                continue

            for node in tree.nodes:

                if not isinstance(
                    node,
                    VFDNode,
                ):
                    continue

                # --------------------------------------------------
                # Update outputs
                # --------------------------------------------------

                try:

                    if "Frequency" in node.outputs:
                        node.outputs[
                            "Frequency"
                        ].default_value = (
                            node.last_command
                        )

                    if "Running" in node.outputs:
                        node.outputs[
                            "Running"
                        ].default_value = (
                            node.running
                        )

                    if "Connected" in node.outputs:
                        node.outputs[
                            "Connected"
                        ].default_value = (
                            node.connected
                        )

                    if "Fault" in node.outputs:
                        node.outputs[
                            "Fault"
                        ].default_value = (
                            node.fault
                        )

                    if "RPM" in node.outputs:
                        node.outputs[
                            "RPM"
                        ].default_value = (
                            node.actual_rpm
                        )

                except Exception:
                    pass

                # --------------------------------------------------
                # Send command
                # --------------------------------------------------

                try:

                    node.update_command()

                except Exception as exc:

                    print(
                        "[VFD] update error:",
                        exc,
                    )

    except Exception as exc:

        print(
            "[VFD] timer error:",
            exc,
        )

    return 0.05


# ============================================================================
# REGISTER
# ============================================================================

classes = (
    VFDValueSocket,
    VFD_OT_connect,
    VFD_OT_disconnect,
    VFD_OT_reset,
    VFDNode,
)


def register():

    global _TIMER_RUNNING

    for cls in classes:

        bpy.utils.register_class(cls)

    # Geometry Nodes menu
    if hasattr(
        bpy.types,
        "NODE_MT_geometry_node_add_all",
    ):

        bpy.types.NODE_MT_geometry_node_add_all.append(
            vfd_node_menu
        )

    # Start timer
    if not bpy.app.timers.is_registered(
        vfd_timer
    ):

        _TIMER_RUNNING = True

        bpy.app.timers.register(
            vfd_timer,
            first_interval=0.1,
            persistent=True,
        )


# ============================================================================
# UNREGISTER
# ============================================================================

def unregister():

    global _TIMER_RUNNING

    _TIMER_RUNNING = False

    try:

        if bpy.app.timers.is_registered(
            vfd_timer
        ):

            bpy.app.timers.unregister(
                vfd_timer
            )

    except Exception:
        pass

    try:

        bpy.types.NODE_MT_geometry_node_add_all.remove(
            vfd_node_menu
        )

    except Exception:
        pass

    try:

        _CONTROLLER.disconnect()

    except Exception:
        pass

    for cls in reversed(classes):

        try:

            bpy.utils.unregister_class(
                cls
            )

        except RuntimeError:

            pass


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":

    register()
