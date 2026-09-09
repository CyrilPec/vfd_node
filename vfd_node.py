bl_info={"name":"VFD Geometry Node","author":"CyrilPec / modified","version":(2,0,0),"blender":(3,6,0),"location":"Geometry Nodes > Add > VFD","description":"HY01D523B VFD controller for Blender Geometry Nodes","category":"Node"}
import bpy
import threading
from bpy.types import Node,Operator
from bpy.props import BoolProperty,FloatProperty,IntProperty,StringProperty
try:
    from .vfd_manager import VFDManager
except ImportError:
    from vfd_manager import VFDManager
_LOCK=threading.RLock()
_MANAGERS={}
_TIMER_RUNNING=False
def manager_for(node):
    key=as_pointer(node)
    manager=_MANAGERS.get(key)
    if manager is None:
        manager=VFDManager()
        _MANAGERS[key]=manager
    return manager
def as_pointer(node):
    try:
        return node.as_pointer()
    except Exception:
        return id(node)
def remove_manager(node):
    key=as_pointer(node)
    manager=_MANAGERS.pop(key,None)
    if manager:
        try:
            manager.stop()
        except Exception:
            pass
        try:
            manager.disconnect()
        except Exception:
            pass
def find_node(name):
    for tree in bpy.data.node_groups:
        for node in tree.nodes:
            if node.name==name:
                return node
    return None
class VFD_OT_connect(Operator):
    bl_idname="vfd.connect"
    bl_label="Connect VFD"
    node_name:StringProperty()
    def execute(self,context):
        node=find_node(self.node_name)
        if node is None:
            self.report({"ERROR"},"VFD node was not found.")
            return {"CANCELLED"}
        if node.connect_vfd():
            self.report({"INFO"},"VFD connected.")
            return {"FINISHED"}
        self.report({"ERROR"},node.console_line)
        return {"CANCELLED"}
class VFD_OT_disconnect(Operator):
    bl_idname="vfd.disconnect"
    bl_label="Disconnect VFD"
    node_name:StringProperty()
    def execute(self,context):
        node=find_node(self.node_name)
        if node is None:
            return {"CANCELLED"}
        node.disconnect_vfd()
        return {"FINISHED"}
class VFD_OT_stop(Operator):
    bl_idname="vfd.stop"
    bl_label="Stop VFD"
    node_name:StringProperty()
    def execute(self,context):
        node=find_node(self.node_name)
        if node is None:
            return {"CANCELLED"}
        if node.stop_vfd():
            self.report({"INFO"},"VFD stopped.")
            return {"FINISHED"}
        self.report({"ERROR"},node.console_line)
        return {"CANCELLED"}
class VFD_OT_reset(Operator):
    bl_idname="vfd.reset"
    bl_label="Reset VFD"
    node_name:StringProperty()
    def execute(self,context):
        node=find_node(self.node_name)
        if node is None:
            return {"CANCELLED"}
        node.reset_status()
        return {"FINISHED"}
class VFDNode(Node):
    bl_idname="VFDNode"
    bl_label="VFD"
    bl_icon="DRIVER"
    serial_port:StringProperty(name="Port",default="COM3")
    slave_id:IntProperty(name="Slave ID",default=4,min=1,max=247)
    baudrate:IntProperty(name="Baud",default=9600,min=1200,max=115200)
    enabled:BoolProperty(name="Enabled",default=True)
    armed:BoolProperty(name="ARM",default=False)
    motor_power_kw:FloatProperty(name="Power",default=1.5,min=0)
    motor_voltage:FloatProperty(name="Voltage",default=220,min=0)
    motor_frequency:FloatProperty(name="Rated Hz",default=400,min=1)
    motor_rpm:FloatProperty(name="Rated RPM",default=24000,min=1)
    minimum_frequency:FloatProperty(name="Min Hz",default=0,min=0)
    maximum_frequency:FloatProperty(name="Max Hz",default=400,min=0)
    minimum_rpm:FloatProperty(name="Min RPM",default=0,min=0)
    maximum_rpm:FloatProperty(name="Max RPM",default=24000,min=0)
    frequency_command:FloatProperty(name="Frequency",default=0,min=0)
    rpm_command:FloatProperty(name="RPM",default=0,min=0)
    running_command:BoolProperty(name="RUN",default=False)
    reverse_command:BoolProperty(name="REVERSE",default=False)
    connected:BoolProperty(name="Connected",default=False)
    running:BoolProperty(name="Running",default=False)
    reverse:BoolProperty(name="Reverse",default=False)
    fault:BoolProperty(name="Fault",default=False)
    fault_code:IntProperty(name="Fault Code",default=0)
    actual_frequency:FloatProperty(name="Frequency",default=0)
    actual_rpm:FloatProperty(name="RPM",default=0)
    actual_current:FloatProperty(name="Current",default=0)
    actual_voltage:FloatProperty(name="Voltage",default=0)
    console_line:StringProperty(name="Console",default="VFD | DISCONNECTED")
    last_error:StringProperty(name="Error",default="")
    @classmethod
    def poll(cls,ntree):
        return ntree.bl_idname=="GeometryNodeTree"
    def init(self,context):
        f=self.inputs.new("NodeSocketFloat","Frequency")
        f.default_value=0.0
        r=self.inputs.new("NodeSocketFloat","RPM")
        r.default_value=0.0
        run=self.inputs.new("NodeSocketBool","RUN")
        run.default_value=False
        rev=self.inputs.new("NodeSocketBool","REVERSE")
        rev.default_value=False
        self.outputs.new("NodeSocketFloat","Frequency")
        self.outputs.new("NodeSocketFloat","RPM")
        self.outputs.new("NodeSocketFloat","Current")
        self.outputs.new("NodeSocketFloat","Voltage")
        self.outputs.new("NodeSocketBool","Connected")
        self.outputs.new("NodeSocketBool","Running")
        self.outputs.new("NodeSocketBool","Reverse")
        self.outputs.new("NodeSocketBool","Fault")
        
    def copy(self,node):
        self.connected=False
        self.armed=False
        self.console_line="VFD | DISCONNECTED"
        _MANAGERS.pop(as_pointer(self),None)
    def free(self):
        remove_manager(self)
    def get_manager(self):
        return manager_for(self)
    def configure(self):
        m=self.get_manager()
        m.configure_connection(self.serial_port,self.slave_id,self.baudrate,0.25)
        m.set_enabled(self.enabled)
        m.set_armed(self.armed)
        return m
    def connect_vfd(self):
        with _LOCK:
            try:
                m=self.configure()
                ok=m.connect()
                self.connected=bool(ok)
                if ok:
                    self.last_error=""
                    self.console_line=f"VFD | CONNECTED | {self.serial_port}"
                else:
                    self.last_error=m.last_error()
                    self.console_line=f"VFD | ERROR | {self.last_error or 'Connection failed'}"
                return ok
            except Exception as e:
                self.connected=False
                self.last_error=str(e)
                self.console_line=f"VFD | ERROR | {e}"
                return False
    def disconnect_vfd(self):
        with _LOCK:
            try:
                self.get_manager().disconnect()
            except Exception:
                pass
        self.connected=False
        self.running=False
        self.console_line="VFD | DISCONNECTED"
    def stop_vfd(self):
        with _LOCK:
            try:
                ok=self.get_manager().stop()
                self.running=False
                self.console_line="VFD | STOPPED" if ok else f"VFD | ERROR | {self.get_manager().last_error()}"
                return ok
            except Exception as e:
                self.console_line=f"VFD | ERROR | {e}"
                return False
    def reset_status(self):
        self.last_error=""
        self.fault=False
        self.fault_code=0
        if self.connected:
            self.console_line="VFD | READY"
        else:
            self.console_line="VFD | DISCONNECTED"
    def socket_float(self,name,default):
        s=self.inputs.get(name)
        if s is None:
            return default
        try:
            if s.is_linked:
                src=s.links[0].from_socket
                if hasattr(src,"default_value"):
                    return float(src.default_value)
            return float(s.default_value)
        except Exception:
            return default
    def socket_bool(self,name,default):
        s=self.inputs.get(name)
        if s is None:
            return default
        try:
            if s.is_linked:
                src=s.links[0].from_socket
                if hasattr(src,"default_value"):
                    return bool(src.default_value)
            return bool(s.default_value)
        except Exception:
            return default
    def calculate_command(self):
        frequency=self.socket_float("Frequency",self.frequency_command)
        rpm=self.socket_float("RPM",self.rpm_command)
        rpm_socket=self.inputs.get("RPM")
        if rpm_socket and rpm_socket.is_linked:
            rated_rpm=max(self.motor_rpm,0.001)
            frequency=(rpm/rated_rpm)*self.motor_frequency
        frequency=max(self.minimum_frequency,min(frequency,self.maximum_frequency))
        rpm=(frequency/max(self.motor_frequency,0.001))*self.motor_rpm
        run=self.socket_bool("RUN",self.running_command)
        reverse=self.socket_bool("REVERSE",self.reverse_command)
        if not self.enabled or not self.armed:
            run=False
        return frequency,rpm,run,reverse
    def apply_command(self):
        if not self.connected:
            return False
        frequency,rpm,run,reverse=self.calculate_command()
        with _LOCK:
            try:
                m=self.configure()
                if not m.is_connected():
                    self.connected=False
                    self.console_line="VFD | DISCONNECTED"
                    return False
                ok=m.apply_command(run,reverse,frequency)
                if ok:
                    self.actual_frequency=frequency
                    self.actual_rpm=rpm
                    self.running=run
                    self.reverse=reverse
                    self.console_line=f"VFD | {'RUN' if run else 'READY'} | {'REV' if reverse else 'FWD'} | {frequency:.1f} Hz | {rpm:.0f} RPM"
                    self.last_error=""
                else:
                    self.last_error=m.last_error()
                    self.console_line=f"VFD | ERROR | {self.last_error or 'Command failed'}"
                return ok
            except Exception as e:
                self.last_error=str(e)
                self.console_line=f"VFD | ERROR | {e}"
                return False
    def update_status(self):
        if not self.connected:
            self._outputs()
            return
        with _LOCK:
            try:
                m=self.get_manager()
                status=m.update_status()
                self.connected=bool(status.connected)
                self.running=bool(status.running)
                self.reverse=bool(status.reverse)
                self.fault=bool(status.fault)
                self.fault_code=int(status.fault_code)
                self.actual_frequency=float(status.frequency_hz)
                self.actual_rpm=float(status.rpm)
                self.actual_current=float(status.current_a)
                self.actual_voltage=float(status.voltage_v)
                if self.fault:
                    self.console_line=f"VFD | FAULT {self.fault_code} | {status.fault_text or 'VFD fault'}"
                elif self.connected:
                    state="RUN" if self.running else "READY"
                    direction="REV" if self.reverse else "FWD"
                    self.console_line=f"VFD | {state} | {direction} | {self.actual_frequency:.1f} Hz | {self.actual_rpm:.0f} RPM"
                else:
                    self.console_line="VFD | DISCONNECTED"
            except Exception as e:
                self.last_error=str(e)
                self.console_line=f"VFD | ERROR | {e}"
        self._outputs()
    def _outputs(self):
        values={"Frequency":self.actual_frequency,"RPM":self.actual_rpm,"Current":self.actual_current,"Voltage":self.actual_voltage,"Connected":self.connected,"Running":self.running,"Reverse":self.reverse,"Fault":self.fault}
        for name,value in values.items():
            s=self.outputs.get(name)
            if s:
                try:
                    s.default_value=value
                except Exception:
                    pass
    def update(self):
        try:
            if self.connected:
                self.apply_command()
            self._outputs()
        except Exception:
            pass
    def draw_buttons(self,context,layout):
        row=layout.row(align=True)
        row.prop(self,"serial_port",text="Port")
        row.prop(self,"slave_id",text="ID")
        row=layout.row(align=True)
        row.prop(self,"baudrate",text="Baud")
        if self.connected:
            op=row.operator("vfd.disconnect",text="Disconnect",icon="UNLINKED")
        else:
            op=row.operator("vfd.connect",text="Connect",icon="LINKED")
        op.node_name=self.name
        row=layout.row(align=True)
        row.prop(self,"enabled",text="Enabled",toggle=True)
        row.prop(self,"armed",text="ARM",toggle=True)
        row=layout.row(align=True)
        row.prop(self,"frequency_command",text="Hz")
        row.prop(self,"rpm_command",text="RPM")
        row=layout.row(align=True)
        row.prop(self,"running_command",text="RUN",toggle=True)
        row.prop(self,"reverse_command",text="REV",toggle=True)
        op=row.operator("vfd.stop",text="STOP",icon="PAUSE")
        op.node_name=self.name
        row=layout.row(align=True)
        row.prop(self,"motor_frequency",text="Rated Hz")
        row.prop(self,"motor_rpm",text="Rated RPM")
        row=layout.row(align=True)
        row.prop(self,"minimum_frequency",text="Min")
        row.prop(self,"maximum_frequency",text="Max")
        status=layout.row()
        status.alert=self.fault
        status.label(text=self.console_line,icon="ERROR" if self.fault else "INFO")
    def draw_label(self):
        return "VFD"
def vfd_node_menu(self,context):
    self.layout.operator("node.add_node",text="VFD",icon="DRIVER").type="VFDNode"
def vfd_timer():
    if not _TIMER_RUNNING:
        return None
    try:
        for tree in bpy.data.node_groups:
            if tree.bl_idname!="GeometryNodeTree":
                continue
            for node in tree.nodes:
                if isinstance(node,VFDNode):
                    node.update_status()
    except Exception as e:
        print(f"[VFD] Timer error: {e}")
    return 0.1
classes=(VFD_OT_connect,VFD_OT_disconnect,VFD_OT_stop,VFD_OT_reset,VFDNode)
def register():
    global _TIMER_RUNNING
    for cls in classes:
        bpy.utils.register_class(cls)
    menu=getattr(bpy.types,"NODE_MT_geometry_node_add_all",None)
    if menu:
        try:
            menu.remove(vfd_node_menu)
        except Exception:
            pass
        menu.append(vfd_node_menu)
    _TIMER_RUNNING=True
    if not bpy.app.timers.is_registered(vfd_timer):
        bpy.app.timers.register(vfd_timer,first_interval=0.2,persistent=True)
def unregister():
    global _TIMER_RUNNING
    _TIMER_RUNNING=False
    try:
        if bpy.app.timers.is_registered(vfd_timer):
            bpy.app.timers.unregister(vfd_timer)
    except Exception:
        pass
    try:
        bpy.types.NODE_MT_geometry_node_add_all.remove(vfd_node_menu)
    except Exception:
        pass
    for manager in list(_MANAGERS.values()):
        try:
            manager.stop()
        except Exception:
            pass
        try:
            manager.disconnect()
        except Exception:
            pass
    _MANAGERS.clear()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
if __name__=="__main__":
    register()
