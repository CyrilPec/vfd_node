bl_info = {
    "name": "VFD Node",
    "author": "CyrilPec",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "Node Editor",
    "description": "VFD control node",
    "category": "Node",
}

import bpy

from .vfd_node import (
    VFDValueSocket,
    VFDStatusSocket,
    VFDNode,
)

classes = (
    VFDValueSocket,
    VFDStatusSocket,
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
