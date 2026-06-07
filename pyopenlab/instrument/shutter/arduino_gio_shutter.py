# -*- coding: utf-8 -*-
"""Serial driver for a simple Arduino shutter with emulated state read-back."""

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.shutter import ShutterWithEmulatedRead


class ArduinoShutter(ShutterWithEmulatedRead, SerialInstrument):
    """Arduino shutter controlled over serial, sending "1" to open and "0" to close."""

    def __init__(self, port):
        """Open the serial connection and flush any startup output.

        Args:
            port: The serial port the Arduino is connected to (e.g. "COM3").
        """
        self.termination_character = '\r'
        SerialInstrument.__init__(self, port)
        ShutterWithEmulatedRead.__init__(self)
        self.flush_input_buffer()
        self.readline()
        self.timeout = 1

    def set_state(self, State):
        """Open or close the shutter, checking the Arduino's acknowledgement.

        Args:
            State: The desired state, "Open" or "Closed". If it already matches
                the current state, nothing is sent.
        """
        if State == self.get_state():
            return print(f'shutter is already {State}')
        if State == 'Open':
            if self.query('1') != '1\n':
                print('error opening shutter')
        if State == 'Closed':
            if self.query('0') != '0\n':
                print('error closing shutter')


if __name__ == '__main__':
    ard = ArduinoShutter('COM3')

    # ard.close_shutter()
    # ard.open_shutter()
    # ard.toggle()
    # ard.toggle()
