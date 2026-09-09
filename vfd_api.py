from __future__ import annotations

from typing import Optional

from .vfd_manager import VFDManager, VFDStatus


class VFDAPI:
    """
    Public interface between Blender and the VFD system.

    Blender/node code should use this class only.

    Architecture:

        Blender
           ↓
        VFDAPI
           ↓
        VFDManager
           ↓
        VFDSession
           ↓
        HY01D523B
    """

    def __init__(self, manager: VFDManager):
        if manager is None:
            raise ValueError(
                "VFDAPI requires a VFDManager."
            )

        self._manager = manager

    # ==================================================================
    # CONNECTION
    # ==================================================================

    def connect(self) -> bool:
        return bool(
            self._manager.connect()
        )

    def disconnect(self) -> None:
        self._manager.disconnect()

    def is_connected(self) -> bool:
        return bool(
            self._manager.is_connected()
        )

    # ==================================================================
    # SAFETY
    # ==================================================================

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        self._manager.set_enabled(
            bool(enabled)
        )

    def set_armed(
        self,
        armed: bool,
    ) -> None:
        self._manager.set_armed(
            bool(armed)
        )

    # ==================================================================
    # COMMAND
    # ==================================================================

    def set_target(
        self,
        frequency_hz: float,
        running: bool,
        reverse: bool,
    ) -> bool:
        """
        Set desired VFD state.

        This validates and queues the command.

        It does NOT wait for the physical VFD to execute it.
        """

        return bool(
            self._manager.set_target(
                frequency_hz=frequency_hz,
                running=running,
                reverse=reverse,
            )
        )

    def stop(self) -> bool:
        """
        Normal software stop.
        """

        return bool(
            self._manager.stop()
        )

    def emergency_stop(self) -> bool:
        """
        Software emergency stop.

        This is not a safety-rated emergency stop.
        Physical STO/safety circuitry is required for machine safety.
        """

        return bool(
            self._manager.emergency_stop()
        )

    # ==================================================================
    # STATUS
    # ==================================================================
    
    def get_status(self) -> VFDStatus:
        """
        Return the latest cached status.

        No serial communication is performed here.
        Safe to call from Blender's timer/node evaluation.
        """

        return self._manager.get_status()

    def refresh_status(self) -> VFDStatus:
        """
        Compatibility alias.

        Status is already refreshed by the VFDSession worker.

        This method intentionally does NOT perform a synchronous
        hardware read.
        """

        return self._manager.get_status()

    # ==================================================================
    # PARAMETERS
    # ==================================================================

    def read_parameter(
        self,
        parameter: int,
    ) -> Optional[int]:
        """
        Read a VFD parameter.

        The actual serial operation is executed by VFDSession's
        worker thread.
        """

        return self._manager.read_parameter(
            parameter
        )

    def write_parameter(
        self,
        parameter: int,
        value: int,
    ) -> bool:
        """
        Write a VFD parameter.

        The actual serial operation is executed by VFDSession's
        worker thread.
        """

        return bool(
            self._manager.write_parameter(
                parameter,
                value,
            )
        )

    # ==================================================================
    # STATE
    # ==================================================================

    @property
    def target_frequency(self) -> float:
        return float(
            self._manager.target.frequency_hz
        )

    @property
    def target_running(self) -> bool:
        return bool(
            self._manager.target.running
        )

    @property
    def target_reverse(self) -> bool:
        return bool(
            self._manager.target.reverse
        )

    # ==================================================================
    # ERROR
    # ==================================================================

    def last_error(self) -> str:
        return str(
            self._manager.last_error()
        )
