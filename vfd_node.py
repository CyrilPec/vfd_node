from __future__ import annotations

import bpy

from bpy.types import Node, NodeSocket
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
    EnumProperty,
)


# ============================================================================
# VFD SOCKET
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
        layout.label(text=text)

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
            "enabled": bool(self.enabled),
            "armed": bool(self.armed),

            "run": bool(self.running_command),
            "reverse": bool(self.reverse_command),
            "reset": bool(self.reset_command),

            "frequency": float(frequency),

            "rpm": float(
                self.frequency_to_rpm(
                    frequency
                )
            ),
        }

    # =========================================================================
    # DRIVER API PLACEHOLDER
    # =========================================================================

    def driver_update(
        self,
        driver,
    ):
        """
        Universal VFD interface.

        The node does NOT know anything about Modbus.

        A future driver receives this logical command and
        translates it into the protocol required by the VFD.
        """

        if driver is None:
            return

        command = self.get_command()

        # Future API:
        #
        # driver.set_enabled(command["enabled"])
        # driver.set_armed(command["armed"])
        # driver.set_run(command["run"])
        # driver.set_reverse(command["reverse"])
        # driver.set_frequency(command["frequency"])
        # driver.reset_fault()
        #
        # status = driver.get_status()

        return command

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
            text=f"Frequency: {self.actual_frequency:.1f} Hz",
        )

        box.label(
            text=f"RPM: {self.actual_rpm:.0f}",
        )

        box.label(
            text=f"Current: {self.actual_current:.2f} A",
        )

        box.label(
            text=f"Voltage: {self.actual_voltage:.1f} V",
        )

        box.label(
            text=f"Power: {self.actual_power:.2f} kW",
        )

        if self.fault:

            row = box.row()

            row.alert = True

            row.label(
                text=f"FAULT: {self.fault_code}",
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
