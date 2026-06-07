# -*- coding: utf-8 -*-
"""Serial driver for the Piezoconcept FOC100 single-axis nanopositioner."""
import serial

import pyopenlab.instrument.serial_instrument as si


class Piezoconcept(si.SerialInstrument):
    """A simple class for the Piezoconcept FOC100 nanopositioning system."""

    def __init__(self, port=None):
        """Open the serial port and recenter the stage to mid-range (50 um).

        Args:
            port (int or str): The port the device is connected to, in any of the
                accepted serial formats.
        """
        self.termination_character = '\n'
        self.port_settings = {
            'baudrate': 115200,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'timeout': 1,  #wait at most one second for a response
            #          'writeTimeout':1, #similarly, fail if writing takes >1s
            #         'xonxoff':False, 'rtscts':False, 'dsrdtr':False,
        }
        si.SerialInstrument.__init__(self, port=port)
        self.recenter()

    def move_rel(self, value, unit="n"):
        """Move the stage by a relative displacement.

        Args:
            value (float): Displacement to move by. Out-of-range moves are
                rejected and an error message is printed.
            unit (str): ``"n"`` for nanometres (default) or ``"u"`` for microns.
        """
        if unit == "n":
            multiplier = 1
        if unit == "u":
            multiplier = 1E3

        if (value * multiplier + self.position) > 1E5 or (value * multiplier + self.position) < 0:
            print("The value is out of range! 0-100 um (0-1E8 nm) (Z)")
        elif (value * multiplier + self.position) < 1E5 and (value * multiplier +
                                                             self.position) >= 0:
            self.write("MOVRX " + str(value) + unit)
            self.position = (value * multiplier + self.position)

    def move(self, value, unit="n"):
        """Move the stage to an absolute position.

        Prints an error to the console if the requested position is outside the
        0-100 um travel range.

        Args:
            value (float): Absolute position to move to.
            unit (str): ``"n"`` for nanometres (default) or ``"u"`` for microns.
        """
        if unit == "n":
            multiplier = 1
        if unit == "u":
            multiplier = 1E3

        if value * multiplier > 1E5 or value * multiplier < 0:
            print("The value is out of range! 0-100 um (0-1E8 nm) (Z)")

        elif value * multiplier < 1E5 and value * multiplier >= 0:
            self.write("MOVEX " + str(value) + unit)
            self.position = value * multiplier

    def move_step(self, direction):
        """Move by one predefined step in the given direction.

        Args:
            direction (int): Sign/multiple of the step to take.

        Note:
            Relies on ``self.stepsize``, which is not initialised by this class,
            so calling this method raises ``AttributeError`` unless ``stepsize``
            has been set externally.
        """
        self.move_rel(direction * self.stepsize)

    def recenter(self):
        """Move the stage to its center position (50 um) and reset position."""
        self.move(50, unit="u")
        self.position = 50E3

    def INFO(self):
        """Query the controller's info string.

        Returns:
            str: The multi-line ``INFOS`` response from the controller.
        """
        return self.query(
            "INFOS",
            multiline=True,
            termination_line="\n \n \n \n",
            timeout=.1,
        )


if __name__ == "__main__":
    '''Basic test, should open the Z stage and print its info before closing. 
    Obvisouly the comport has to be correct!'''
    Z = Piezoconcept(port="COM9")
    print(Z.INFO())
    Z.close()
