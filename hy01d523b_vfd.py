import threading
import time
import serial

class HY01D523BError(Exception):
    pass

class HY01D523B:
    MODEL="HY01D523B"
    SOFTWARE_VERSION="1.21"
    CONTROL_DATA_NAMES=("target_frequency","output_frequency","output_current","rpm","dc_voltage","ac_voltage","control","temperature")
    def __init__(self,serial_port=None,slave_id=4,baudrate=9600,timeout=0.25):
        self.serial=serial_port
        self.slave_id=slave_id
        self.baudrate=baudrate
        self.timeout=timeout
        self.frequency_hz=0.0
        self.running=False
        self.reverse=False
        self.last_error=""
        self._lock=threading.Lock()
    def set_serial(self,serial_port):
        self.serial=serial_port
    def is_connected(self):
        return bool(self.serial and getattr(self.serial,"is_open",False))
    def connect(self):
        if not self.serial:
            raise HY01D523BError("Serial port is not configured")
        if not self.serial.is_open:
            self.serial.open()
        return self.is_connected()
    def disconnect(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.running=False
    def _crc16_modbus(self,data):
        crc=0xFFFF
        for byte in data:
            crc^=byte
            for _ in range(8):
                crc=(crc>>1)^0xA001 if crc&1 else crc>>1
        return bytes((crc&0xFF,(crc>>8)&0xFF))
    def _send(self,data,read_size=0):
        if not self.is_connected():
            raise HY01D523BError("VFD is not connected")
        frame=bytes(data)+self._crc16_modbus(data)
        with self._lock:
            self.serial.reset_input_buffer()
            self.serial.write(frame)
            self.serial.flush()
            if not read_size:
                return b""
            response=self.serial.read(read_size)
        if len(response)!=read_size:
            raise HY01D523BError(f"Invalid response length: {len(response)}/{read_size}")
        return response
    def _check_response(self,response,function):
        if len(response)<5:
            raise HY01D523BError("Response too short")
        if response[0]!=self.slave_id:
            raise HY01D523BError(f"Invalid slave ID: {response[0]}")
        if response[1]!=(function&0xFF):
            raise HY01D523BError(f"Invalid function: 0x{response[1]:02X}")
        if response[-2:]!=self._crc16_modbus(response[:-2]):
            raise HY01D523BError("CRC error")
        return response
    def _write_raw(self,data):
        return self._send(data,0)
    def _read_response(self,data,size):
        return self._send(data,size)
    def forward(self):
        result=self._write_raw([self.slave_id,0x03,0x01,0x01])
        self.running=True
        self.reverse=False
        return 1
    def reverse_run(self):
        result=self._write_raw([self.slave_id,0x03,0x01,0x02])
        self.running=True
        self.reverse=True
        return 1
    def run(self):
        result=self._write_raw([self.slave_id,0x03,0x01,0x00])
        self.running=True
        return 1
    def stop(self):
        result=self._write_raw([self.slave_id,0x03,0x01,0x08])
        self.running=False
        return 1
    def set_frequency(self,frequency_hz):
        frequency_hz=float(frequency_hz)
        if not 0.0<=frequency_hz<=400.0:
            raise HY01D523BError("Frequency must be between 0 and 400 Hz")
        value=round(frequency_hz*100)
        data=[self.slave_id,0x05,0x02,(value>>8)&0xFF,value&0xFF]
        self._write_raw(data)
        self.frequency_hz=frequency_hz
        return 1
    def read_parameter(self,parameter):
        parameter=int(parameter)
        if not 0<=parameter<=182:
            raise HY01D523BError("Parameter must be PD000..PD182")
        data=[self.slave_id,0x01,(parameter>>8)&0xFF,parameter&0xFF,0,0]
        response=self._read_response(data,9)
        self._check_response(response,0x01)
        if response[2]!=3:
            raise HY01D523BError("Invalid parameter response")
        return (response[4]<<8)|response[5]
    def write_parameter(self,parameter,value):
        parameter=int(parameter)
        value=int(value)
        if not 0<=parameter<=182:
            raise HY01D523BError("Parameter must be PD000..PD182")
        if not 0<=value<=65535:
            raise HY01D523BError("Parameter value out of range")
        data=[self.slave_id,0x02,(parameter>>8)&0xFF,parameter&0xFF,(value>>8)&0xFF,value&0xFF]
        response=self._read_response(data,9)
        self._check_response(response,0x02)
        return 1
    def read_control_data(self,index):
        index=int(index)
        if not 0<=index<8:
            raise HY01D523BError("Control-data index must be 0..7")
        data=[self.slave_id,0x04,0x03,index,0,0]
        response=self._read_response(data,8)
        self._check_response(response,0x04)
        if response[2]!=3 or response[3]!=index:
            raise HY01D523BError("Invalid control-data response")
        return (response[4]<<8)|response[5]
    def read_control_status(self):
        values={}
        for index,name in enumerate(self.CONTROL_DATA_NAMES):
            raw=self.read_control_data(index)
            if index in (0,1,2):
                values[name]=raw/100.0
            else:
                values[name]=raw
        values.update({
            "connected":self.is_connected(),
            "running":self.running,
            "reverse":self.reverse,
            "frequency":values["target_frequency"],
            "fault":False,
            "fault_code":0,
            "error":self.last_error
        })
        return values
    def get_local_status(self):
        return {
            "connected":self.is_connected(),
            "running":self.running,
            "reverse":self.reverse,
            "frequency":self.frequency_hz,
            "fault":False,
            "fault_code":0,
            "error":self.last_error
        }
    def command(self,name,*args):
        commands={
            "forward":self.forward,
            "reverse":self.reverse_run,
            "run":self.run,
            "stop":self.stop,
            "set_frequency":self.set_frequency
        }
        if name not in commands:
            raise HY01D523BError(f"Unknown command: {name}")
        return commands[name](*args)
