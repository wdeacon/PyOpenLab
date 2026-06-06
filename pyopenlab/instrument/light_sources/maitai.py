# -*- coding: utf-8 -*-
"""Serial driver and Qt control widget for the Spectra-Physics MaiTai Ti:sapphire laser."""

from builtins import str

import numpy as np
import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty


class Maitai(SerialInstrument):
    """Serial interface to a MaiTai Ti:sapphire laser.

    Note:
        :meth:`set_wavelength` builds its out-of-range log message with
        ``'... (' + wavelength + ')'`` where ``wavelength`` is a number, which raises
        ``TypeError`` instead of logging. Left unfixed as a behavioural defect.
    """

    port_settings = dict(
        baudrate=38400,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  #wait at most one second for a response
        writeTimeout=1,  #similarly, fail if writing takes >1s
        xonxoff=True,
        rtscts=False,
        dsrdtr=False,
    )
    termination_character = "\n"

    def __init__(self, port):
        """Open the laser on the given serial port and disable the watchdog timer.

        Args:
            port: Serial port name (e.g. ``'COM1'``).
        """
        super(Maitai, self).__init__(port)
        self.set_watchdog(0)

    def on(self):
        """Turn the MaiTai on."""
        self.write('ON')

    def off(self):
        """Turn the MaiTai off."""
        self.write('OFF')

    def open_shutter(self):
        """Open the shutter via the :attr:`shutter_state` property."""
        self.shutter_state = True

    def close_shutter(self):
        """Close the shutter via the :attr:`shutter_state` property."""
        self.shutter_state = False

    def get_shutter_state(self):
        """Get the shutter state as a bool.

        Returns:
            bool: ``True`` if the shutter is open, ``False`` if closed.
        """
        return bool(int(self.query('SHUTTER?')))

    def set_shutter_state(self, state):
        """Set the shutter from a bool.

        Args:
            state: ``True`` to open the shutter, ``False`` to close it.
        """
        self.write('SHUTTER ' + str(int(state)))

    shutter_state = NotifiedProperty(get_shutter_state, set_shutter_state)

    def get_humidity(self):
        """Return the laser's internal relative humidity reading."""
        return self.query('READ:HUM?')

    def get_power(self):
        """Return the IR output power."""
        return self.query('READ:POWER?')

    def get_green_power(self):
        """Return the green pump-laser power."""
        return self.query('READ:PLASER:POWER?')

    def get_current_wavelength(self):
        """Return the live wavelength, used to check whether tuning to the set value is done."""
        return self.query('READ:WAVELENGTH?')

    current_wavelength = property(get_current_wavelength)

    def save(self):
        """Save the current MaiTai settings so they persist across a restart."""
        self.write('SAVE')

    def get_set_wavelength(self):
        """Return the configured target wavelength in nm.

        Returns:
            The set wavelength (between 690 and 1020 nm) as a float.
        """
        return float(self.query('WAVELENGTH?')[:-2])


#    def set_wavelength(self,wavelength):
#        if wavelength>690 and wavelength<1020:
#            return self.write('WAVELENGTH ')
#        else:
#            self.log('Wavelength out of range ('+wavelength+')')

    def set_wavelength(self, wavelength):
        """Set the target wavelength in nm; values outside 690-1020 nm are rejected.

        Args:
            wavelength: Target wavelength in nm.
        """
        if wavelength > 690 and wavelength < 1020:
            return self.write('WAVelength ' + str(wavelength))
        else:
            self.log('Wavelength out of range (' + wavelength + ')')

    wavelength = NotifiedProperty(get_set_wavelength, set_wavelength)

    def set_watchdog(self, n):
        """Set the watchdog timeout in seconds.

        The watchdog is the time the laser stays on without a keep-alive command; ``0``
        disables it.

        Args:
            n: Watchdog timeout in seconds (``0`` to disable).
        """
        self.write('TIMER:WATCHDOG ' + str(n))

    def get_qt_ui(self):
        """Return a :class:`MaitaiControlUI` control widget for this laser."""
        return MaitaiControlUI(self)


class MaitaiControlUI(QuickControlBox):
    """Control widget for the MaiTai laser."""

    def __init__(self, maitai):
        super(MaitaiControlUI, self).__init__(title='MaiTai')
        self.maitai = maitai
        self.add_button('on')
        self.add_button('off')
        self.add_button('open_shutter')
        self.add_button('close_shutter')
        self.add_doublespinbox("wavelength")
        self.auto_connect_by_name(controlled_object=self.maitai)
