from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .vfd_manager import VFDManager, VFDStatus


@dataclass(frozen=True)
class VFDTarget:
    frequency_hz: float
    running: bool
    reverse: bool


class VFDAPI:
    """
    Public interface between Blender and the VFD system.

    Blender should use this class instead of accessing the driver directly.
    """

    def __init__(self, manager: VFDManager):
        self._manager = manager

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        return self._manager.connect()

    def disconnect(self) -> None:
        self._manager.disconnect()

    def is_connected(self) -> bool:
        return self._manager.is_connected()

    # ------------------------------------------------------------------
    # SAFETY
    # ------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self._manager.set_enabled(enabled)

    def set_armed(self, armed: bool) -> None:
        self._manager.set_armed(armed)

    # ------------------------------------------------------------------
    # COMMAND
    # ------------------------------------------------------------------

    def set_target(
        self,
        frequency_hz: float,
        running: bool,
        reverse: bool,
    ) -> bool:
        return self._manager.apply_command(
            run=running,
            reverse=reverse,
            frequency_hz=frequency_hz,
        )

    def stop(self) -> bool:
        return self._manager.stop()

    def emergency_stop(self) -> bool:
        return self._manager.emergency_stop()

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_status(self) -> VFDStatus:
        return self._manager.get_status()

    def refresh_status(self) -> VFDStatus:
        """
        Temporary synchronous refresh.

        This will later be moved behind the communication session.
        """
        return self._manager.update_status()

    # ------------------------------------------------------------------
    # PARAMETERS
    # ------------------------------------------------------------------

    def read_parameter(self, parameter: int) -> Optional[int]:
        return self._manager.read_parameter(parameter)

    def write_parameter(
        self,
        parameter: int,
        value: int,
    ) -> bool:
        return self._manager.write_parameter(
            parameter,
            value,
        )

    # ------------------------------------------------------------------
    # ERRORS
    # ------------------------------------------------------------------

    def last_error(self) -> str:
        return self._manager.last_error()
