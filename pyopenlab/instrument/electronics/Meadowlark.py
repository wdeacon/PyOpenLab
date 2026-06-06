# -*- coding: utf-8 -*-
"""Serial control of a Meadowlark liquid-crystal variable retarder (CellDrive 3000)."""

import time

from serial import EIGHTBITS
from serial import PARITY_NONE
from serial import STOPBITS_ONE

from pyopenlab.instrument.serial_instrument import SerialInstrument


class VariableRetarder(SerialInstrument):
    r"""Serial control of a Meadowlark D3040 variable retarder.

    Does not provide all the functionality of the CellDrive 3000 Advanced software. Commands must
    be sent ending in ``\r`` but replies end in ``\r\n``, so the read/write functions are overridden.

    Note:
        The :attr:`all_voltages` setter formats a list with ``'ldd:%d,%d,%d,%d' % integers``; ``%``
        with a list (not a tuple) raises ``TypeError``, so setting all voltages is broken.
    """
    port_settings = dict(baudrate=38400,
                         bytesize=EIGHTBITS,
                         parity=PARITY_NONE,
                         stopbits=STOPBITS_ONE,
                         timeout=2)
    termination_character = '\r'
    termination_read = '\r\n'
    wait_time = 2

    def __init__(self, port=None, channel=1):
        """Open the serial connection and set the default channel.

        Args:
            port (str, optional): Serial port name. If None, the port is auto-detected.
            channel (int): Default LC channel for single-channel queries and writes.
        """
        super(VariableRetarder, self).__init__(port)
        self._channel = channel

    def query(self, queryString, *args, **kwargs):
        """Query the device and return the value after the command echo.

        Args:
            queryString (str): Command to send (without the termination character).
            *args: Forwarded to the base query.
            **kwargs: Forwarded to the base query.

        Returns:
            str: The portion of the reply following the ``':'`` separator.
        """
        reply = super(VariableRetarder, self).query(queryString, *args, **kwargs)
        self._logger.debug('Received: %s' % reply)
        split_reply = reply.split(':')
        split_query = queryString.split(':')
        if split_reply[0] != split_query[0]:
            self._logger.warn('Error trying to query: %s %s' % (queryString, split_reply))
        return split_reply[1]

    @property
    def firmware_version(self):
        """str: Firmware version string reported by the device."""
        return self.query('ver:?')

    @property
    def channel(self):
        """int: Default LC channel that single-channel queries and writes act on."""
        return self._channel

    @channel.setter
    def channel(self, value):
        self._channel = value

    @property
    def voltage(self):
        """float: Modulation voltage on the current channel, in volts."""
        reply = self.query('ld:%d,?' % self.channel)
        integer = int(reply.split(',')[1])
        voltage = integer / 6553.5
        return voltage

    @voltage.setter
    def voltage(self, value):
        """Set the modulation (square-wave amplitude) voltage on the current channel.

        Args:
            value (float): Voltage in volts; must be between 0 and 10.

        Raises:
            AssertionError: If ``value`` is outside ``[0, 10]``.
        """
        assert 0 <= value <= 10
        integer = value * 6553.5
        self.write('ld:%d,%d' % (self.channel, integer))
        time.sleep(self.wait_time)

    @property
    def all_voltages(self):
        """list of float: Modulation voltages on all four LC channels, in volts."""
        reply = self.query('ldd:?')
        integers = list(map(int, reply.split(',')))
        voltages = [x / 6553.5 for x in integers]
        return voltages

    @all_voltages.setter
    def all_voltages(self, value):
        """Simultaneously set the modulation voltages on all four LC channels.

        Args:
            value (tuple): Four voltages in volts; each must be between 0 and 10.

        Raises:
            AssertionError: If any voltage is outside ``[0, 10]``.
        """
        for val in value:
            assert 0 <= val <= 10
        voltages = tuple(value)
        integers = [x * 6553.5 for x in voltages]
        self.write('ldd:%d,%d,%d,%d' % integers)

    @property
    def temperature(self):
        """float: Current temperature of a temperature-controlled LC, in degrees Celsius."""
        integer = int(self.query('tmp:?'))
        return (integer * 500 // 65535) - 273.15

    @property
    def temperature_setpoint(self):
        """float: Current temperature setpoint, in degrees Celsius."""
        integer = int(self.query('tsp:?'))
        return (integer * 500 // 16384) - 273.15

    @temperature_setpoint.setter
    def temperature_setpoint(self, value):
        """Set the temperature setpoint for temperature control.

        Args:
            value (float): Setpoint temperature in degrees Celsius.
        """
        integer = (value + 273.15) * 16384 / 500
        self.write('tsp:%d' % integer)

    def sync(self):
        """Produce a sync pulse (high-low) on the front-panel sync connector."""
        self.write('sout:')

    def extin(self, channels):
        """Enable output channels to be driven by the front-panel external input connector.

        Args:
            channels (tuple): Four booleans selecting which channels follow the external input.
        """
        integer = 0
        for idx, chn in enumerate(channels):
            if chn:
                integer += 2**idx
        self.write('extin:%d' % integer)
