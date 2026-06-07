# -*- coding: utf-8 -*-
"""Serial driver for the Southampton custom (IL) shutter."""

import time

import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.shutter import ShutterWithEmulatedRead


class ILShutter(SerialInstrument, ShutterWithEmulatedRead):
    """Southampton custom shutter controlled over serial.

    On connection it enables computer control with the ``ct`` command, then
    raises ("S4U") or lowers ("S4D") the shutter via :meth:`set_state`.
    """

    def __init__(self, port):
        """Open the serial connection and enable computer control.

        Args:
            port: The serial port the shutter is connected to (e.g. "COM3").
        """
        self.port_settings = {
            'baudrate': 19200,
            'bytesize': serial.SEVENBITS,
            'parity': serial.PARITY_ODD,
            'stopbits': serial.STOPBITS_ONE,
            'timeout': 1,  #wait at most one second for a response
            'writeTimeout': 1,  #similarly, fail if writing takes >1s
        }
        self.termination_character = "\r"
        SerialInstrument.__init__(self, port=port)
        ShutterWithEmulatedRead.__init__(self)
        self.query("ct")  #enable computer control

    def set_state(self, value):
        """Set the shutter to be either "Open" or "Closed".

        Args:
            value: The desired state, "Open" or "Closed" (case insensitive).

        Note:
            This writes the result to ``self.__state`` (name-mangled to
            ``_ILShutter__state``), which is never read back. Emulated read-back
            relies on ``_last_set_state`` from
            :class:`~pyopenlab.instrument.shutter.ShutterWithEmulatedRead`, which
            this override does not update. Left unchanged to avoid behaviour
            change.
        """
        if value.title() == "Open":
            self.query("S4U")
            self.__state = "Open"
        else:
            self.query("S4D")
            self.__state = "Closed"


if __name__ == "__main__":
    shutter = ILShutter("COM3")
    shutter.show_gui()
    time.sleep(1)
    shutter.expose(1)
    print(ILShutter.get_instances())  #Check there's not two here...
