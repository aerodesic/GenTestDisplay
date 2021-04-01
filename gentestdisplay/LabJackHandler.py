#
# LabJack driver class
#
import syslog
from labjack import ljm
from threading import Thread, RLock
import platform
import json
from copy import deepcopy
import re

LJD_SYSTEM_NOT_SUPPORTED            = 1
LJD_FILE_ERROR                      = 2
LJD_NOT_A_VALID_REGISTER            = 3
LJD_LABJACK_NOT_FOUND               = 4
LJD_UNKNOWN_TYPE                    = 5
LJD_REGISTER_NOT_READABLE           = 6
LJD_REGISTER_NOT_WRITABLE           = 7
LJD_INVALID_CHANNEL_TYPE            = 8
LJD_STREAMING_IN_PROGRESS           = 9
LJD_STREAMING_REQUIRES_CALLBACK     = 10
LJD_STREAMING_REQUIRES_CHANNELS     = 11

LABJACK_MODELS = {
    4: u"T4",
    7: u"T7",
}

LABJACK_MODELS_INVERTED = {
    LABJACK_MODELS[model]: model for model in LABJACK_MODELS
}

# Connections accepted
LABJACK_CONNECTIONS = {
    1: u"USB",
    4: u"TCP",
}

LABJACK_CONNECTIONS_INVERTED = {
    LABJACK_CONNECTIONS[connection]: connection for connection in LABJACK_CONNECTIONS
}

class LabJackException(Exception):
    def __init__(self, message, code=-1):
        super(LabJackException, self).__init__(message)
        self.code = code

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "%s [%d]" % (self.message, self.code)

# An instance of a device
class LabJackDevice():
    def __init__(self, driver, handle, connection, model, serial_number):
        self.driver = driver
        self.handle = handle
        self.model = model
        self.connection = connection
        self.serial_number = serial_number
        self.lock = RLock()
        self.__streaming = False
        self.__stream_callback = None
        self.__stream_completion = None
        self.__channels = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.Close()

    def __str__(self):
        return "LJ model %d connection %d sn %s" % (self.model, self.connection, self.serial_number)

    def SetChannelList(self, channels):
        self.__channels = channels

    def GetChannelList(self):
        return self.__channels

    def StreamStart(self, channels=None, scans_per_read=24, scan_rate = 1.0, callback=None):
        if self.__streaming:
            raise LabJackException("Streaming in progress", LJD_STREAMING_IN_PROGRESS)

        if callback is None:
            raise LabJackException("Streaming requires callback", LJD_STREAMING_REQUIRES_CALLBACK)

        if channels is None:
            raise LabJackException("Streaming requires one or more channels", LJD_STREAMING_REQUIRES_CHANNELS)

        addresses = ljm.namesToAddresses(len(channels), channels)[0]

        self.__streaming = True
        self.__stream_callback = callback
        rc = ljm.eStreamStart(self.handle, scans_per_read, len(addresses), addresses, scan_rate)
        ljm.setStreamCallback(self.handle, self.__stream_thread_callback)

        return rc

    def __stream_thread_callback(self, handle):
        values = ljm.eStreamRead(handle)
        self.__stream_callback(handle, values)


    def StreamStop(self):
        if self.__streaming:
            self.__streaming = False
            ljm.eStreamStop(self.handle)
            self.__stream_completion = self.__stream_callback(self.handle, None)
        else:
            self.__stream_completion = False

        return self.__stream_completion

    
    def ReadRegister(self, name):
        with self.lock:
            if name not in self.driver.registers:
                raise LabJackException("%s not a register", LJD_NOT_A_VALID_REGISTER)

            type_info = self.driver._typeraw(name)
            print("Read: type_info for %s is %s" % (name, type_info))

            if 'R' not in self.driver.registers[name]['readwrite']:
                raise LabJackException("Cannot read %s" % name, LJD_REGISTER_NOT_READABLE)

            if type_info in [ "INT16", "INT32", "UINT16", "UINT32" ]:
                value = int(ljm.eReadName(self.handle, name))

            elif type_info in [ "STRING" ]:
                value = ljm.eReadNameString(self.handle, name)

            elif type_info in [ "FLOAT32", "FLOAT64" ]:
                value = ljm.eReadName(self.handle, name)

            else:
                raise LabJackException("%s type unknown for %s" % (type_info, name), LJD_UNKNOWN_TYPE)


            info = self.driver.registers[name]
            if "constants" in info:
                if value in info["constants"]:
                    value = info["constants"][value]

            return value

    def WriteRegister(self, name, value):
        with self.lock:
            if name not in self.driver.registers:
                raise LabJackException("%s not a register", LJD_NOT_A_VALID_REGISTER)

            type_info = self.driver._typeraw(name)
            print("Read: type_info for %s is %s" % (name, type_info))

            if 'W' not in self.driver.registers[name]['readwrite']:
                raise LabJackException("Cannot read %s" % name, LJD_REGISTER_NOT_WRITABLE)

            if type_info in [ "INT16", "INT32", "UINT16", "UINT32" ]:
                ljm.eWriteName(self.handle, name, int(value))

            elif type_info in [ "STRING" ]:
                value = ljm.eWriteNameString(self.handle, name, str(value))

            elif type_info in [ "FLOAT32", "FLOAT64" ]:
                value = ljm.eWriteName(self.handle, float(name))

            else:
                raise LabJackException("%s type unknown for %s" % (type_info, name), LJD_UNKNOWN_TYPE)


    def Close(self):
        print("Close called")
        with self.lock:
            self.driver.Close(self)
            self.handle = None

    def __del__(self):
        print("__del__ called")
        self.Close()


class LabJackHandler():
    def __init__(self, constants_file=None):
        self.available_devices = None
        self.max_channels = { "AIN": 16, "DIO": -1, "DAC": -1 }
        self.sn_in_use = {}
        self.lock = RLock()
        self.config_dialog = None

        if constants_file == None:
            if platform.system() == "Linux" or platform.system() == "macos":
                self.constants_file = "/usr/local/share/LabJack/LJM/ljm_constants.json"
            elif platform.system() == "Windows":
                self.constants_file = "C:/ProgramData/LabJack/LJM/ljm_constants.json"
            else:
                raise LabJackException("Platform %s not supported", LJD_SYSTEM_NOT_SUPPORTED)
        else:
            self.constants_file = constants_file

        with self.lock:
            try:
                with open(self.constants_file, "r") as f:
                    self.constants = json.loads(f.read())
            except Exception as e:
                raise LabJackException(str(e), LJD_FILE_ERROR)
        
        # Invert by register name
        self.registers = {}
        reg_info = re.compile(r"([a-zA-Z0-9]+)#\(([0-9]+):([0-9]+)\)(_.*)")

        for reg in self.constants["registers"]:
            v = reg_info.match(reg["name"])

            if v:
                # print("%s" % reg["name"])
                # Special enumerative case
                head = v.group(1)
                start = int(v.group(2))
                end = int(v.group(3))
                rest = v.group(4)
                address = int(reg["address"])
                # print("%s*_%s from %d to %d base address %d" % (head, rest, start, end, address))

                # Add a channels descriptor
                channels_descriptor = "CHANNEL_GROUP_%s" % (head)
                self.registers[channels_descriptor] = deepcopy(reg)
                self.registers[channels_descriptor]['first_channel'] = start
                self.registers[channels_descriptor]['last_channel'] = end

                for point in range(start, end + 1):
                    name = "%s%d%s" % (head, point, rest)
                    self.registers[name] = deepcopy(reg)
                    self.registers[name]['name'] = name
                    self.registers[name]["address"] = address
                    address += 1

            else:
                self.registers[reg["name"]] = deepcopy(reg)

        # Invert constant fields within register by name
        for name in self.registers:
            if "constants" in self.registers[name]:
                constants = self.registers[name]["constants"]
                self.registers[name]["constants"] = { constant["value"]: constant["name"] for constant in constants }

            # Fix up register's 'device' entry so a test of <model> in ['devices'] will work
            if "devices" in self.registers[name]:
                devices = self.registers[name]["devices"]
                if len(devices) != 0 and isinstance(devices[0], dict):
                    # Array of dictionaries: turn into list of dictionaries (remove 'device' entry in each...
                    new_devices = {}
                    for device in devices:
                        new_devices[device["device"]] = device
                        del(new_devices[device["device"]]['device'])

                    self.registers[name]["devices"] = new_devices 



    def GetMaxChannels(self, channel_type):
        return self.max_channels[channel_type] if channel_type in self.max_channels else -1

    def SetMaxChannels(self, channel_type, max_channels):
        if channel_type not in self.max_channels:
            raise LabJackException("'%s' is not a valid channel type" % channel_type, code = LJD_INVALID_CHANNEL_TYPE)

        self.max_channels[channel_type] = max_channels
        
    def SetExtendedChannels(self, extended=True):
        if extended:
            self.SetMaxChannels("AIN", 194)
            self.SetMaxChannels("DIO", 22)
            self.SetMaxChannels("DAC", 2)
        else:
            self.SetMaxChannels("AIN", 16)
            self.SetMaxChannels("DIO", -1)
            self.SetMaxChannels("DAC", -1)

        
    # Required.  Return dialog for configuring this device's configuration
    def GetConfigDialog(self):
        return self.config_dialog

    def SetConfigDialog(self, dialog=None):
        self.config_dialg = dialog

    # Required.  Return available devices
    def AvailableDevices(self, callback=None, force=False):
        if self.available_devices is None or force:
            if callback is not  None:
                # Create a thread to do the work and call back when done
                thread = Thread(target = self._scan_thread, kwargs = {'callback': callback, 'force': force})
                thread.start()

                # Signal we are waiting for a callback
                available = None

            else:
                # No callback so we have to do it here.
                with self.lock:
                    # Look for any labjacks anywhere
                    results = ljm.listAllS("ANY", "ANY")

                    # Becomes a list of found sn's with model and connections
                    self.available_devices = {}

                    for index in range(results[0]):
                        sn = str(results[3][index])
                        model = results[1][index]
                        if model in LABJACK_MODELS:
                            model = LABJACK_MODELS[model]

                            connection = results[2][index]
                            if connection in LABJACK_CONNECTIONS:
                                connection = LABJACK_CONNECTIONS[connection]

                                # Remove model and connections seen for each serial number
                                if sn not in self.available_devices:
                                    self.available_devices[sn] = { 'model': model, 'connections': [ connection ] }
                                else:
                                    if connection not in self.available_devices[sn]['connections']:
                                        self.available_devices[sn]['connections'].append(connection)
    
                    available = self.available_devices

        else:
            available = self.available_devices

        return available

    def _scan_thread(self, callback, force):
        callback(self.AvailableDevices(force=force))

    # Required. Return list of available channel name
    chantypes = { 'AIN': "_BINARY", "DIO": "_EF_READ_A", "DAC": "_BINARY" }

    def GetChannelList(self, devtype):
        channels = []
        for chantype in self.chantypes:
            for channel in range(0, self.max_channels[chantype]):
                channel_name = "%s%d" % (chantype, channel)
                channel_full_name = channel_name + self.chantypes[chantype]
                if channel_full_name in self.registers:
                    if 'devices' in self.registers[channel_full_name] and devtype in self.registers[channel_full_name]['devices']:
                        channels.append(channel_name)

        return channels

    # Required.  Open a device and return a device instance
    def Open(self, serial_number, model = "ANY", connection = "ANY"):
        with self.lock:
            # sn_in_use = { <serial number> : 'device': <device instance>, 'use': <count> }
            if serial_number in self.sn_in_use:
                # Already in use, return handle and don't re-open
                self.sn_in_use[serial_number]['use'] += 1

            else:

                # Not in use, so open it and put into sn_in_use table
                try:
                    handle = ljm.openS(str(model), str(connection), str(serial_number))

                except Exception as e:
                    print("openS returned '%s'" % str(e))
                    raise LabJackException(e.message, code = LJD_LABJACK_NOT_FOUND)
      
                device = LabJackDevice(self, handle, 0, connection, str(serial_number))

                device.SetChannelList(self.GetChannelList(str(model)))

                self.sn_in_use[serial_number] = { 'device':  device, 'use': 1 }


            return self.sn_in_use[serial_number]['device']

    # Required.  Called with the device by user or by Device when device is Closed or delete.
    def Close(self, device):
        with self.lock:
            # Checking to see if sn is in list will guard against a recursion loop between this Close and the device Close
            if device.serial_number in self.sn_in_use:
                if self.sn_in_use[device.serial_number]['use'] == 1:
                    # Fetch the device handler descriptor
                    device = self.sn_in_use[device.serial_number]['device']
                    # Delete the table entry
                    del(self.sn_in_use[device.serial_number])

                    # delete the device
                    del(device)
                else:
                    print("sn_in_use is %s" % self.sn_in_use)
                    self.sn_in_use[device.serial_number]['use'] -= 1

    def _typeraw(self, name):
        with self.lock:
            try:
                return self.registers[name]["type"]

            except Exception as e:
                raise LabJackException(e.message, code=LJD_NOT_A_VALID_REGISTER)

    # Required. Return value type for point
    def Type(self, name):
        with self.lock:
            info = self.registers[name]
            return "STRING" if "constants" in info else info["type"]


_SINGLETON_HANDLER = None
_SINGLETON_HANDLER_LOCK = RLock()

def GetLabJackHandler():
    global _SINGLETON_HANDLER_LOCK
    global _SINGLETON_HANDLER

    with _SINGLETON_HANDLER_LOCK:
        if _SINGLETON_HANDLER is None:
            _SINGLETON_HANDLER = LabJackHandler()

        return _SINGLETON_HANDLER


