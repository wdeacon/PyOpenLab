# -*- coding: utf-8 -*-
"""Serial driver for the Integrated Optics MatchBox laser."""

import numpy as np
import serial

from pyopenlab.instrument.light_sources import LightSource
from pyopenlab.instrument.serial_instrument import SerialInstrument


class MatchboxLaser(SerialInstrument, LightSource):
    """Serial interface to an Integrated Optics MatchBox laser.

    Note:
        Several methods parse responses with ``np.fromstring(..., dtype=np.float, ...)``.
        ``np.float`` was removed in NumPy 1.24+ and ``np.fromstring`` is deprecated, so
        these calls fail on modern NumPy. Left unfixed as a dependency-compatibility issue.
    """

    def __init__(self, port=None):
        self.port_settings = {
            'baudrate': 115200,
            'bytesize': serial.EIGHTBITS,
            'stopbits': serial.STOPBITS_ONE,
            'timeout': 1,  #wait at most one second for a response
            'writeTimeout': 1,  #similarly, fail if writing takes >1s
        }
        self.termination_character = "\r"
        SerialInstrument.__init__(self, port=port)
        self.turn_on()

    def __del__(self):
        self.turn_off()
        return

    def close(self):
        self.turn_off()
        self.__del__()

    def turn_on(self):
        """Turn the laser on."""
        self.query("e 1")

    def turn_off(self):
        """Turn the laser off."""
        self.query("e 0")

    def get_power(self):
        """Read the current power output in mW.

        Returns:
            The measured optical power in mW.
        """
        readings = self.query("r r")
        readout = np.fromstring(readings[11:], dtype=np.float, sep=' ', count=4)
        return readout[3]

    def readpower(self):
        """Deprecated alias for :meth:`get_power`."""
        return self.get_power()

    def read_setParameters(self):
        """Read the configured ("set") parameters from the laser.

        Returns:
            An 8-element array: set T1 (deg), set T2 (deg), set LD current (mA), set optical
            power (12-bit range), set optical power (mW), max allowed LD current (mA),
            autostart enable (bool), and access level (float).
        """
        readings = self.query("r s")
        settings = np.fromstring(readings, dtype=np.float, sep=' ', count=8)
        return settings

    def read_parameters(self):
        """Read the live operating parameters and print the LD (DAC) current.

        Returns:
            A 4-element array of live readings (T1, T2, T3, LD current); the LD current is
            also printed.
        """
        readings = self.query("r r")
        readout = np.fromstring(readings[11:], dtype=np.float, sep=' ', count=4)
        DAC = readout[3]
        print("DAC current:  %.2f mA" % DAC)
        return readout

    def set_power(self, power):
        """Set the optical-power DAC over its full 12-bit range.

        The value is coerced to a non-negative integer (via ``abs(int(power))``); the upper
        bound of 8191 is not enforced here. This does not turn the laser off.

        Args:
            power: Requested DAC value (0-8191).

        Returns:
            The measured power after setting, from :meth:`get_power`.
        """
        power = abs(int(power))
        print("Setting power:{} (min:0, max: 8191)".format(power))
        self.query("c 6 {}".format(power))
        return self.get_power()


if __name__ == "__main__":
    laser = MatchboxLaser("/dev/ttyUSB0")
    laserID = laser.query("ID?")
    laserName = laser.query("NM?")
    laser.show_gui()
    laser.close()
