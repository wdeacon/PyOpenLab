# -*- coding: utf-8 -*-
"""Serial driver for the Inspire optical parametric oscillator (OPO)."""

from builtins import str

import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.utils.notified_property import NotifiedProperty


class inspire_OPO(SerialInstrument):
    """Serial interface to an Inspire OPO.

    Note:
        ``__init__`` never calls ``SerialInstrument.__init__`` and ignores its ``port``
        argument, so the serial connection is never opened; ``initialise`` then issues a
        ``write`` with no open port. ``enable_power_mode`` references a bare ``mode_dict``
        rather than ``self.mode_dict`` and will raise ``NameError``. These are pre-existing
        bugs left unfixed.
    """

    port_settings = dict(
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  #wait at most one second for a response
        writeTimeout=1,  #similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    def __init__(self, port):
        self.mode = 'power'
        self.initialise()

    def initialise(self):
        self.write('00 550.0')

    def set_wavelength(self, wavelength):
        """Send a wavelength to the OPO using the command code for the current mode.

        Args:
            wavelength: Target wavelength in nm; truncated to an integer before sending.
        """
        wavelength = str(int(wavelength)) + '.0'
        self.write(self.mode_dict[self.mode] + wavelength)

    def get_wavelength(self):
        """Query the OPO wavelength.

        Returns:
            The raw wavelength response string from the instrument.
        """
        wavelength = self.query('50 550.0')
        return wavelength

    wavelength = NotifiedProperty(get_wavelength, set_wavelength)

    def enable_power_mode(self):
        """Switch the OPO into power-tracking mode at the current wavelength."""
        self.query(mode_dict['power'] + ' ' + self.wavelength)

    mode_dict = {'tune': '03', 'power': '04'}

    def SHG_on(self):
        self.query('08 000.0')

    def SHG_off(self):
        self.query('09 000.0')

    def SHG_find(self):
        self.query('10 000.0')

    def SHG_optimise(self):
        self.query('11 000.0')

    def auto_cavity(self):
        self.query('07 ' + self.wavelength)


#    def get_spectrum(self):
