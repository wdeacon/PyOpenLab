# -*- coding: utf-8 -*-
"""
Modified from https://github.com/plasmon360/python_newport_1918_powermeter

"""

from ctypes import *
import time

import numpy as np

from pyopenlab.instrument import Instrument


class NewportPowermeter(Instrument):
    """Driver for the Newport 1918 USB optical power meter (via ``usbdll.dll``)."""

    def __init__(self, product_id, **kwargs):
        """Load the USB DLL and open the device.

        Args:
            product_id: USB product id of the meter. Find it in Device Manager
                under the instrument's Details > Hardware IDs; e.g. for
                ``PID_ABC1`` pass ``0xABC1``.
            **kwargs: Optional ``libname`` to override the default
                ``usbdll.dll``.
        """
        super(NewportPowermeter, self).__init__()
        if "libname" in kwargs:
            libname = kwargs["libname"]
        else:
            libname = "usbdll.dll"
        self.dll = windll.LoadLibrary(libname)

        self.product_id = product_id

        self.open_device_with_product_id()
        self.instrument = self.get_instrument_list()
        self.device_id, self.model_number, self.serial_number = self.instrument

        self.wvl_range = [int(self.query('PM:MIN:Lambda?')), int(self.query('PM:MAX:Lambda?'))]

    # def __del__(self):
    #     self.close_device()

    def _dllWrapper(self, command, *args):
        """Call a DLL function by name and check its status code.

        Args:
            command: Name of the DLL function to call.
            *args: Arguments forwarded to the DLL function.

        Raises:
            Exception: If the DLL call returns a non-zero status.
        """
        self._logger.debug("Calling DLL with: %s %s" % (command, args))
        status = getattr(self.dll, command)(*args)
        if status != 0:
            raise Exception('%s failed with status %s' % (command, status))
        else:
            pass

    def open_device_all_products_all_devices(self):
        """Open every connected Newport USB device."""
        self._dllWrapper("newp_usb_init_system")
        self._logger.info("You have connected to one or more Newport products")

    def open_device_with_product_id(self):
        """Open the USB device matching :attr:`product_id`."""
        cproductid = c_int(self.product_id)
        useusbaddress = c_bool(1)  # We will only use deviceids or addresses
        num_devices = c_int()

        self._dllWrapper("newp_usb_open_devices", cproductid, useusbaddress, byref(num_devices))

    def close_device(self):
        """Close all open Newport USB devices and release the driver."""
        self._dllWrapper("newp_usb_uninit_system")

    def get_instrument_list(self):
        """Query the connected instrument's identifiers.

        Returns:
            list: ``[device_id, model_number, serial_number]``.
        """
        arInstruments = c_int()
        arInstrumentsModel = c_int()
        arInstrumentsSN = c_int()
        nArraySize = c_int()
        self._dllWrapper("GetInstrumentList", byref(arInstruments), byref(arInstrumentsModel),
                         byref(arInstrumentsSN), byref(nArraySize))
        instrument_list = [arInstruments.value, arInstrumentsModel.value, arInstrumentsSN.value]
        return instrument_list

    def query(self, query_string):
        """Write a command and read the device's response.

        Args:
            query_string: Command to send; see the manual, e.g. ``'*IDN?'``.

        Returns:
            The device's response string.
        """
        self.write(query_string)
        return self.read()

    def read(self):
        """Read an ASCII response from the device.

        Returns:
            bytes: The response with trailing CR/LF stripped.
        """
        cdevice_id = c_long(self.device_id)
        time.sleep(0.2)
        response = create_string_buffer(('\000' * 1024).encode())
        leng = c_ulong(1024)
        read_bytes = c_ulong()
        self._dllWrapper("newp_usb_get_ascii", cdevice_id, byref(response), leng, byref(read_bytes))
        answer = response.value[0:read_bytes.value].rstrip(b'\r\n')
        return answer

    def write(self, command_string):
        """Write a command string to the device.

        Args:
            command_string: Command to send; see the manual for commands.
        """
        command = create_string_buffer(command_string.encode())
        length = c_ulong(sizeof(command))
        cdevice_id = c_long(self.device_id)

        self._dllWrapper("newp_usb_send_ascii", cdevice_id, byref(command), length)

    @property
    def channel(self):
        """The active detector channel (1 or 2)."""
        return self.query("PM:CHANnel?")

    @channel.setter
    def channel(self, channel):
        assert channel in [1, 2]

        self.write("PM:CHANnel " + str(channel))

    @property
    def wavelength(self):
        """The detector's operating wavelength in nm."""
        self._logger.debug("Reading wavelength")
        return self.query('PM:Lambda?')

    @wavelength.setter
    def wavelength(self, wavelength):
        """Set the wavelength on the device.

        Args:
            wavelength: Wavelength to set; coerced to ``int`` and checked
                against :attr:`wvl_range`.
        """
        self._logger.debug("Setting wavelength")
        if not isinstance(wavelength, int):
            self._logger.info('Wavelength has to be an integer. Converting to integer')
            wavelength = int(wavelength)
        assert self.wvl_range[0] <= wavelength <= self.wvl_range[1]

        self.write('PM:Lambda ' + str(wavelength))

    def set_filtering(self, filter_type=0):
        """Set the device's filtering mode.

        Args:
            filter_type: 0 (none), 1 (analog), 2 (digital) or 3 (analog and
                digital).

        Raises:
            ValueError: If ``filter_type`` is not in 0-3.
        """
        if filter_type in [0, 1, 2, 3]:
            self.write("PM:FILT %d" % filter_type)
        else:
            raise ValueError("filter_type needs to be between 0 and 3")

    def read_buffer(self, wavelength=700, buff_size=1000, interval_ms=1):
        """Acquire a buffer of power readings and return their statistics.

        Args:
            wavelength: Wavelength in nm to measure at.
            buff_size: Number of readings to acquire.
            interval_ms: Time between readings in ms.

        Returns:
            list: ``[actual_wavelength, mean_power, std_power]``.
        """
        self.wavelength = wavelength
        self.write('PM:DS:Clear')
        self.write('PM:DS:SIZE ' + str(buff_size))
        self.write(
            'PM:DS:INT ' + str(interval_ms * 10)
        )  # to set 1 ms rate we have to give int value of 10. This is strange as manual says the INT should be in ms
        self.write('PM:DS:ENable 1')
        while int(self.query('PM:DS:COUNT?')) < buff_size:  # Waits for the buffer is full or not.
            time.sleep((0.001 * interval_ms * buff_size) / 10)
        actualwavelength = self.query('PM:Lambda?')
        mean_power = self.query('PM:STAT:MEAN?')
        std_power = self.query('PM:STAT:SDEV?')
        self.write('PM:DS:Clear')
        return [actualwavelength, mean_power, std_power]

    @property
    def power(self):
        """float: The instantaneous power reading."""
        power = self.query('PM:Power?')
        return float(power)


if __name__ == '__main__':
    nd = NewportPowermeter(0xCEC7)
    nd._logger.setLevel("DEBUG")
    print('Init finished')
    print(nd.get_instrument_list())
    print(nd.wavelength)
    print(nd.power)
    print(nd.wavelength)
    print(nd.power)
