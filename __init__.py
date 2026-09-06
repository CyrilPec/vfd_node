bl_info = {
    "name": "VFD Node",
    "author": "CyrilPec",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "Node Editor > Add > VFD",
    "description": "Control a Huanyang HY01D523B VFD from Blender.",
    "category": "Node",
}
from . import vfd_node

def register():
    vfd_node.register()

def unregister():
    vfd_node.unregister()

if __name__ == "__main__":
    register()

