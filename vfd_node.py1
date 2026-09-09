from __future__ import annotations

import bpy

from bpy.types import Node

from .vfd_api import VFDAPI
from .vfd_manager import VFDStatus


# ----------------------------------------------------------------------
# API / MANAGER REGISTRY
# ----------------------------------------------------------------------

# One API instance per physical VFD configuration.
#
# The important part is that nodes do NOT each open their own serial
# connection.
#
# This registry will eventually be backed by a connection/session
# manager.
_APIS = {}


def _api_key(port: str, slave_id: int) -> tuple:
    return (
        str(port),
        int(slave_id),
    )


def get_vfd_api(
    port: str,
    slave_id: int,
) -> VFDAPI:
    key = _api_key(port, slave_id)

    api = _APIS.get(key)

    if api is None:
        # Import here to avoid circular imports.
        from .vfd_session import VFDSession
        from .vfd_manager import VFDManager

        session = VFDSession(
            port=port,
            slave_id=slave_id,
        )

        manager = VFDManager(
            session=session,
        )

        api = VFDAPI(
            manager=manager,
        )

        _APIS[key] = api

    return api


def release_vfd_api(
    port: str,
    slave_id: int,
) -> None:
    key = _api_key(port, slave_id)

    api = _APIS.pop(key, None)

    if api is None:
        return

    try:
        api.disconnect()
    except Exception:
        pass


# ----------------------------------------------------------------------
# BLENDER NODE
# ----------------------------------------------------------------------

class VFDNode(Node):
    """
    Blender-side adapter for a VFD.

    IMPORTANT:

        This class must not perform direct serial/Modbus I/O.

    Blender:
        Node -> API -> Manager -> Session -> Driver -> VFD
    """

    bl_idname = "VFDNodeType"
    bl_label = "VFD"
    bl_icon = "MOD_PHYSICS"

    # ------------------------------------------------------------------
    # PROPERTIES
    # ------------------------------------------------------------------

    port: bpy.props.StringProperty(
        name="Port",
        default="COM3",
    )

    slave_id: bpy.props.IntProperty(
        name="Slave ID",
        default=4,
        min=1,
        max=247,
    )

    connected: bpy.props.BoolProperty(
        name="Connected",
        default=False,
    )

    enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=True,
    )

    armed: bpy.props.BoolProperty(
        name="Armed",
        default=False,
    )

    frequency_hz: bpy.props.FloatProperty(
        name="Frequency",
        default=0.0,
        min=0.0,
        max=400.0,
        update=lambda self, context: self._command_changed(),
    )

    run: bpy.props.BoolProperty(
        name="Run",
        default=False,
        update=lambda self, context: self._command_changed(),
    )

    reverse: bpy.props.BoolProperty(
        name="Reverse",
        default=False,
        update=lambda self, context: self._command_changed(),
    )

    # ------------------------------------------------------------------
    # CACHED OUTPUT VALUES
    # ------------------------------------------------------------------

    actual_frequency_hz: bpy.props.FloatProperty(
        name="Actual Frequency",
        default=0.0,
    )

    actual_rpm: bpy.props.FloatProperty(
        name="Actual RPM",
        default=0.0,
    )

    actual_running: bpy.props.BoolProperty(
        name="Actual Running",
        default=False,
    )

    actual_reverse: bpy.props.BoolProperty(
        name="Actual Reverse",
        default=False,
    )

    fault: bpy.props.BoolProperty(
        name="Fault",
        default=False,
    )

    fault_code: bpy.props.IntProperty(
        name="Fault Code",
        default=0,
    )

    error_message: bpy.props.StringProperty(
        name="Error",
        default="",
    )

    # ------------------------------------------------------------------
    # INTERNAL STATE
    # ------------------------------------------------------------------

    _last_command = None
    _last_api_key = None

    # ------------------------------------------------------------------
    # BLENDER NODE SETUP
    # ------------------------------------------------------------------

    def init(self, context):
        self.width = 220

        # Inputs
        self.inputs.new(
            "NodeSocketFloat",
            "Frequency",
        )

        self.inputs.new(
            "NodeSocketBool",
            "Run",
        )

        self.inputs.new(
            "NodeSocketBool",
            "Reverse",
        )

        # Outputs
        self.outputs.new(
            "NodeSocketFloat",
            "Frequency",
        )

        self.outputs.new(
            "NodeSocketFloat",
            "RPM",
        )

        self.outputs.new(
            "NodeSocketBool",
            "Running",
        )

        self.outputs.new(
            "NodeSocketBool",
            "Reverse",
        )

        self.outputs.new(
            "NodeSocketBool",
            "Fault",
        )

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def _get_api(self) -> VFDAPI:
        return get_vfd_api(
            port=self.port,
            slave_id=self.slave_id,
        )

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def connect_vfd(self) -> bool:
        api = self._get_api()

        try:
            result = api.connect()

        except Exception as exc:
            self.connected = False
            self.error_message = str(exc)
            return False

        self.connected = bool(result)

        if not self.connected:
            self.error_message = (
                api.last_error()
            )

        else:
            self.error_message = ""

        return self.connected

    def disconnect_vfd(self) -> None:
        api = self._get_api()

        try:
            api.stop()
        except Exception:
            pass

        try:
            api.disconnect()
        except Exception:
            pass

        self.connected = False

        self._clear_outputs()

    # ------------------------------------------------------------------
    # COMMAND CHANGES
    # ------------------------------------------------------------------

    def _command_changed(self) -> None:
        """
        Called when Blender properties change.

        This does NOT directly access the serial port.

        It only asks the API/manager to accept the desired state.
        The communication layer decides when/how to transmit it.
        """

        if not self.connected:
            return

        self._submit_target()

    def _submit_target(self) -> bool:
        api = self._get_api()

        frequency = float(
            self.frequency_hz
        )

        running = bool(
            self.run
        )

        reverse = bool(
            self.reverse
        )

        # --------------------------------------------------------------
        # Local deduplication.
        #
        # The manager also deduplicates, so this is only an additional
        # protection against Blender repeatedly invoking the callback.
        # --------------------------------------------------------------

        command = (
            frequency,
            running,
            reverse,
            bool(self.enabled),
            bool(self.armed),
        )

        if command == self._last_command:
            return True

        self._last_command = command

        try:
            api.set_enabled(
                self.enabled
            )

            api.set_armed(
                self.armed
            )

            result = api.set_target(
                frequency_hz=frequency,
                running=running,
                reverse=reverse,
            )

        except Exception as exc:
            self.error_message = str(exc)
            return False

        if not result:
            self.error_message = (
                api.last_error()
            )
            return False

        self.error_message = ""

        return True

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def update_status(self) -> None:
        """
        Update Blender outputs from CACHED API state.

        IMPORTANT:
        Do not call refresh_status() here.

        This function must remain cheap because Blender can call it
        frequently.
        """

        api = self._get_api()

        try:
            status = api.get_status()

        except Exception as exc:
            self.error_message = str(exc)
            return

        self._apply_status(
            status
        )

    def _apply_status(
        self,
        status: VFDStatus,
    ) -> None:

        self.connected = bool(
            status.connected
        )

        self.actual_frequency_hz = float(
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

        self.actual_running = bool(
            getattr(
                status,
                "running",
                False,
            )
        )

        self.actual_reverse = bool(
            getattr(
                status,
                "reverse",
                False,
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
            ) or 0
        )

        self.error_message = str(
            getattr(
                status,
                "last_error",
                "",
            ) or ""
        )

        self._update_outputs()

    # ------------------------------------------------------------------
    # OUTPUTS
    # ------------------------------------------------------------------

    def _update_outputs(self) -> None:
        if not self.outputs:
            return

        self._set_output(
            "Frequency",
            self.actual_frequency_hz,
        )

        self._set_output(
            "RPM",
            self.actual_rpm,
        )

        self._set_output(
            "Running",
            self.actual_running,
        )

        self._set_output(
            "Reverse",
            self.actual_reverse,
        )

        self._set_output(
            "Fault",
            self.fault,
        )

    def _set_output(
        self,
        name: str,
        value,
    ) -> None:
        socket = self.outputs.get(name)

        if socket is not None:
            socket.default_value = value

    def _clear_outputs(self) -> None:
        self.actual_frequency_hz = 0.0
        self.actual_rpm = 0.0
        self.actual_running = False
        self.actual_reverse = False
        self.fault = False
        self.fault_code = 0

        self._update_outputs()

    # ------------------------------------------------------------------
    # NODE UPDATE
    # ------------------------------------------------------------------

    def update(self) -> None:
        """
        Blender node update callback.

        CRITICAL RULE:
        Never perform synchronous hardware I/O here.

        The desired command is submitted through the API only when
        Blender changes the node state.
        """

        self._update_outputs()

    # ------------------------------------------------------------------
    # OPTIONAL EXPLICIT REFRESH
    # ------------------------------------------------------------------

    def refresh_from_vfd(self) -> bool:
        """
        Explicit hardware refresh.

        This should normally be called by the communication worker,
        not by Blender's node evaluation.

        Kept here only for manual/debug use.
        """

        if not self.connected:
            return False

        api = self._get_api()

        try:
            status = api.refresh_status()

        except Exception as exc:
            self.error_message = str(exc)
            return False

        if status is None:
            return False

        self._apply_status(status)

        return True


# ----------------------------------------------------------------------
# BLENDER UI
# ----------------------------------------------------------------------

class VFDNodePropertiesPanel:
    """
    Optional helper for drawing node properties.

    Keep UI code separate from communication logic.
    """

    @staticmethod
    def draw(
        node: VFDNode,
        layout,
    ):
        layout.prop(
            node,
            "port",
        )

        layout.prop(
            node,
            "slave_id",
        )

        layout.separator()

        layout.prop(
            node,
            "enabled",
        )

        layout.prop(
            node,
            "armed",
        )

        layout.separator()

        layout.prop(
            node,
            "frequency_hz",
        )

        layout.prop(
            node,
            "run",
        )

        layout.prop(
            node,
            "reverse",
        )

        layout.separator()

        row = layout.row()

        if node.connected:
            row.operator(
                "vfd.disconnect",
                text="Disconnect",
            )
        else:
            row.operator(
                "vfd.connect",
                text="Connect",
            )

        if node.error_message:
            box = layout.box()
            box.label(
                text=node.error_message,
                icon="ERROR",
            )


# ----------------------------------------------------------------------
# OPERATORS
# ----------------------------------------------------------------------

class VFD_OT_Connect(bpy.types.Operator):
    bl_idname = "vfd.connect"
    bl_label = "Connect VFD"

    def execute(self, context):
        node = context.active_node

        if not isinstance(node, VFDNode):
            return {"CANCELLED"}

        if node.connect_vfd():
            return {"FINISHED"}

        return {"CANCELLED"}


class VFD_OT_Disconnect(bpy.types.Operator):
    bl_idname = "vfd.disconnect"
    bl_label = "Disconnect VFD"

    def execute(self, context):
        node = context.active_node

        if not isinstance(node, VFDNode):
            return {"CANCELLED"}

        node.disconnect_vfd()

        return {"FINISHED"}


# ----------------------------------------------------------------------
# STATUS TIMER
# ----------------------------------------------------------------------

_STATUS_TIMER_RUNNING = False


def vfd_status_timer():
    """
    Blender-side status refresh.

    IMPORTANT:
        This function must ONLY read cached status.

    The communication worker is responsible for talking to the VFD.
    """

    for tree in bpy.data.node_groups:
        if not hasattr(tree, "nodes"):
            continue

        for node in tree.nodes:
            if not isinstance(node, VFDNode):
                continue

            try:
                node.update_status()
            except Exception:
                # Never allow one broken node to kill the timer.
                continue

    return 0.1


def register_status_timer():
    global _STATUS_TIMER_RUNNING

    if _STATUS_TIMER_RUNNING:
        return

    if not bpy.app.timers.is_registered(
        vfd_status_timer
    ):
        bpy.app.timers.register(
            vfd_status_timer,
            first_interval=0.1,
            persistent=True,
        )

    _STATUS_TIMER_RUNNING = True


def unregister_status_timer():
    global _STATUS_TIMER_RUNNING

    try:
        if bpy.app.timers.is_registered(
            vfd_status_timer
        ):
            bpy.app.timers.unregister(
                vfd_status_timer
            )
    except Exception:
        pass

    _STATUS_TIMER_RUNNING = False


# ----------------------------------------------------------------------
# REGISTER
# ----------------------------------------------------------------------

CLASSES = (
    VFDNode,
    VFD_OT_Connect,
    VFD_OT_Disconnect,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    register_status_timer()


def unregister():
    unregister_status_timer()

    # Disconnect all shared API sessions.
    for api in list(_APIS.values()):
        try:
            api.disconnect()
        except Exception:
            pass

    _APIS.clear()

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
