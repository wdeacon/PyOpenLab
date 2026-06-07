# -*- coding: utf-8 -*-
"""Serial driver for the Uniblitz shutter controller on the BX51 white-light path."""

import time

import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.shutter import ShutterWithEmulatedRead


class Uniblitz(ShutterWithEmulatedRead, SerialInstrument):
    """Uniblitz shutter controller for the BX51 white-light path.

    Sends ``@`` to open and ``A`` to close over the serial line.

    Note:
        :meth:`toggle` compares ``self.shutter_state`` (set to the integers 0/1
        elsewhere) against the strings "Open"/"Closed", so neither branch ever
        matches and toggling does nothing. ``shutter_state`` is also kept
        separately from the inherited ``_last_set_state`` used for emulated
        read-back, so the two can disagree. Left unchanged pending hardware
        verification.
    """

    def __init__(self, port=None):
        """Open the serial connection to the Uniblitz controller.

        Args:
            port: The serial port the controller is connected to (e.g. "COM6").
        """
        self.port_settings = {
            'baudrate': 9600,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'timeout': 1,  #wait at most one second for a response
            'writeTimeout': 1,  #similarly, fail if writing takes >1s
        }
        self.termination_character = "\r"
        SerialInstrument.__init__(self, port=port)
        ShutterWithEmulatedRead.__init__(self)
        self.shutter_state = 0

    def set_state(self, state):
        """Open or close the shutter by writing the command byte.

        Args:
            state: The desired state, "Open" or "Closed".
        """
        if state == 'Open':
            self.ser.write(str.encode('@'))
        elif state == 'Closed':
            self.ser.write(str.encode('A'))

    def toggle(self):
        """Toggle the shutter based on ``self.shutter_state``.

        Note:
            See the class docstring: ``shutter_state`` holds integers, so the
            string comparisons here never match and this is effectively a no-op.
        """
        if self.shutter_state == 'Open':
            self.close_shutter()
        elif self.shutter_state == 'Closed':
            self.open_shutter()

    def open_shutter(self):
        """Open the shutter and record the state."""
        # Writing through the instrument class fails on some setups with
        # "'ser' does not have an attribute 'outWaiting'", so write directly.
        self.ser.write(str.encode('@'))
        self.shutter_state = 1

    def close_shutter(self):
        """Close the shutter and record the state."""
        self.ser.write(str.encode('A'))
        self.shutter_state = 0


if __name__ == '__main__':

    shutter = Uniblitz('COM6')
    # shutter.show_gui()
    shutter.set_state('Open')
    time.sleep(1)
    shutter.set_state('Closed')
