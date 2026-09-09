bl_info = {
    "name": "VFD Node",
    "author": "CyrilPec",
    "version": (1, 2, 0),
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

def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

    self._last_command = None
    self._last_api_key = None

if __name__ == "__main__":
    register()
