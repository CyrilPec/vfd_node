bl_info = {
    "name": "VFD Node",
    "author": "CyrilPec",
    "version": (1, 0, 1),
    "blender": (3, 6, 0),
    "location": "Node Editor",
    "description": "VFD control node",
    "category": "Node",
}

import bpy

from .vfd_node import (
    VFDValueSocket,
    VFDStatusSocket,
    VFD_OT_console_execute,
    VFD_OT_connect,
    VFD_OT_disconnect,
    VFDNode,
)


classes = (
    VFDValueSocket,
    VFDStatusSocket,
    VFD_OT_console_execute,
    VFD_OT_connect,
    VFD_OT_disconnect,
    VFDNode,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
    register()
