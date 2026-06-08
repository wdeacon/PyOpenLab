# -*- coding: utf-8 -*-
"""Serial driver for the Ondax laser."""

from contextlib import closing

import serial

from pyopenlab.instrument.light_sources import LightSource
from pyopenlab.instrument.serial_instrument import SerialInstrument


class OndaxLaser(SerialInstrument, LightSource):
    """Serial interface to an Ondax laser, with power limited to 12-70 mW."""

    def __init__(self, port=None):
        self.port_settings = {
            'baudrate': 9600,
            'bytesize': serial.EIGHTBITS,
            'stopbits': serial.STOPBITS_ONE,
            'parity': serial.PARITY_NONE,
            'timeout': 1,  #wait at most one second for a response
            'writeTimeout': 1,  #similarly, fail if writing takes >1s
        }
        self.termination_character = "\r\n"
        SerialInstrument.__init__(self, port=port)
        LightSource.__init__(self)
        self.min_power = 12
        self.max_power = 70

    def get_power(self):
        """Read the current power output in mW.

        Returns:
            The output power in mW.
        """
        return self.float_query("rli?")

    def readpower(self):
        """Deprecated alias for :meth:`get_power`."""
        return self.get_power()

    def set_power(self, power):
        """Set the power output in mW.

        Args:
            power: Requested output power in mW.

        Returns:
            The measured power after setting, from :meth:`readpower`.

        Raises:
            AssertionError: If ``power`` is above ``max_power`` or below ``min_power``.
        """
        power = float(power)
        assert power <= self.max_power, ValueError("Exceeded maximum power")
        assert power >= self.min_power, ValueError("Below minimum power")
        self.query("slc:%f" % power)
        return self.readpower()


if __name__ == "__main__":
    laser = OndaxLaser("COM1")
    with closing(laser):
        laser.show_gui()
    laser.close()
