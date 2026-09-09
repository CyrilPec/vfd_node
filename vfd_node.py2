from __future__ import annotations

import bpy
from bpy.types import Node

from .vfd_api import VFDAPI
from .vfd_manager import VFDStatus


# ----------------------------------------------------------------------
# SHARED API REGISTRY
# ----------------------------------------------------------------------

# One VFDAPI per physical VFD configuration.
#
# This prevents multiple nodes pointing at the same:
#
#     port + slave_id
#
# from opening multiple serial connections.
_APIS: dict[tuple[str, int], VFDAPI] = {}


def _api_key(
    port: str,
    slave_id: int,
) -> tuple[str, int]:
    return (
        str(port),
        int(slave_id),
    )


def get_vfd_api(
    port: str,
    slave_id: int,
) -> VFDAPI:

    key = _api_key(
        port,
        slave_id,
    )

    api = _APIS.get(key)

    if api is None:
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

    key = _api_key(
        port,
        slave_id,
    )

    api = _APIS.pop(
        key,
        None,
    )

    if api is None:
        return

    try:
        api.stop()
    except Exception:
        pass

    try:
        api.disconnect()
    except Exception:
        pass


# ----------------------------------------------------------------------
# BLENDER NODE
# ----------------------------------------------------------------------

class VFDNode(Node):
    """
    Blender adapter.

    IMPORTANT:

        This class never talks directly to HY01D523B.

        Node
          ↓
        VFDAPI
          ↓
        VFDManager
          ↓
        VFDSession
          ↓
        Worker
          ↓
        HY01D523B
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
        update=lambda self, context:
            self._command_changed(),
    )

    run: bpy.props.BoolProperty(
        name="Run",
        default=False,
        update=lambda self, context:
            self._command_changed(),
    )

    reverse: bpy.props.BoolProperty(
        name="Reverse",
        default=False,
        update=lambda self, context:
            self._command_changed(),
    )

    # ------------------------------------------------------------------
    # CACHED OUTPUTS
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
    # NODE INSTANCE STATE
    # ------------------------------------------------------------------

    def init(self, context):
        self.width = 220

        # IMPORTANT:
        #
        # These are instance attributes.
        #
        # Do NOT make them class attributes because multiple VFDNode
        # instances must not share command history.

        self._last_command = None
        self._last_api_key = None

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

        key = _api_key(
            self.port,
            self.slave_id,
        )

        api = get_vfd_api(
            port=self.port,
            slave_id=self.slave_id,
        )

        # Track which shared API this node is using.
        self._last_api_key = key

        return api

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

        if self.connected:
            self.error_message = ""

            # Immediately read cached state.
            self.update_status()

        else:
            self.error_message = (
                api.last_error()
            )

        return self.connected

    def disconnect_vfd(self) -> None:

        api = self._get_api()

        try:
            api.stop()
        except Exception:
            pass

        release_vfd_api(
            self.port,
            self.slave_id,
        )

        self.connected = False

        self._last_command = None
        self._last_api_key = None

        self._clear_outputs()

    # ------------------------------------------------------------------
    # COMMAND CHANGES
    # ------------------------------------------------------------------

    def _command_changed(self) -> None:
        """
        Blender property callback.

        No hardware I/O occurs here.

        Only the desired state is submitted to VFDAPI.
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

        enabled = bool(
            self.enabled
        )

        armed = bool(
            self.armed
        )

        command = (
            frequency,
            running,
            reverse,
            enabled,
            armed,
        )

        # --------------------------------------------------------------
        # Node-level deduplication.
        #
        # The manager/session also deduplicate.
        #
        # This prevents Blender callbacks from even entering the
        # control layer when nothing actually changed.
        # --------------------------------------------------------------

        if command == self._last_command:
            return True

        try:
            api.set_enabled(
                enabled
            )

            api.set_armed(
                armed
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

        # Only update the deduplication state after successful
        # acceptance by the API.
        self._last_command = command

        self.error_message = ""

        return True

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def update_status(self) -> None:
        """
        Read cached status only.

        NEVER performs RS-485/Modbus communication.
        """

        api = self._get_api()

        try:
            status = api.get_status()

        except Exception as exc:
            self.error_message = str(exc)
            return

        if status is None:
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

        socket = self.outputs.get(
            name
        )

        if socket is None:
            return

        # Only assign if value actually changed.
        #
        # This reduces unnecessary Blender dependency updates.
        if socket.default_value != value:
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
        Blender node update.

        Deliberately does not send anything to the VFD.

        Property update callbacks handle desired-state changes.
        """

        self._update_outputs()

    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------

    def free(self):
        """
        Called when Blender removes this node.
        """

        try:
            release_vfd_api(
                self.port,
                self.slave_id,
            )
        except Exception:
            pass

        self._last_command = None
        self._last_api_key = None
