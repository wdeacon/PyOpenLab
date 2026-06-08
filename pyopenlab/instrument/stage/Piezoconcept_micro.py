# -*- coding: utf-8 -*-
"""Serial driver for the Piezoconcept objective collar nanopositioner."""
import time

import numpy as np
import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.stage import Stage


class Piezoconcept(SerialInstrument, Stage):
    """A class for the Piezoconcept objective collar."""
    axis_names = ('z',)

    def __init__(self, port=None, unit='u', cmd_axis='Z'):
        """Set up the serial port and configure the command axis and units.

        Args:
            port (int or str): The port the device is connected to, in any of
                the accepted serial formats.
            unit (str): Default distance unit, ``'u'`` for microns or ``'n'``
                for nanometres.
            cmd_axis (str): The controller axis letter used in commands.
        """
        self.termination_character = '\n'
        self.port_settings = {
            'baudrate': 115200,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'timeout': 1,  # wait at most one second for a response
            #          'writeTimeout':1, #similarly, fail if writing takes >1s
            #         'xonxoff':False, 'rtscts':False, 'dsrdtr':False,
        }
        SerialInstrument.__init__(self, port=port)
        Stage.__init__(self)
        self.cmd_axis = cmd_axis.upper()
        self.unit = unit  # This can be 'u' for micron or 'n' for nano
        self.distance_scale = 1 if unit == 'n' else 1_000.

    def move(self, value, axis=None, relative=False):
        """Move to a position between 0 and 100 um.

        Out-of-range moves are rejected with a logged warning.

        Args:
            value (float): Position (or displacement, if ``relative``) to move,
                in the configured ``unit``.
            axis (optional): Accepted for API compatibility; ignored
                (single-axis device).
            relative (bool): If True, move relative to the current position.
        """
        nm = int(self.distance_scale * value)
        if relative:
            if 0 <= nm / 1_000 + self.position * 1_000 < 100_000:
                self.write(f'MOVR{self.cmd_axis} {nm}n')
            else:
                self._logger.warn("The value is out of range! 0-100 um (0-1E8 nm) (Z)")
        else:
            if 0 <= nm < 100_000:
                #     if (multiplied-0.2*self.distance_scale) > 0:
                #         value = value-0.2*self.distance_scale  # why?

                self.write(f'MOVE{self.cmd_axis} {nm}n')
                # print(self.readline(), 'reply')
            else:
                self._logger.warn("The value is out of range! 0-100 um (0-1E8 nm) (Z)")

    def get_position(self):
        """Query the controller for the current position.

        Returns:
            float: The current axis position in nanometres.
        """
        return float(self.query(f'GET_{self.cmd_axis}')[:-3])

    def move_step(self, direction):
        """Move by a predefined step in either direction.

        Args:
            direction (int): +1/-1 for positive or negative direction.

        Note:
            There is no value checking on ``direction``, so it can also be used
            to perform integer multiples of the step size. This class defines
            neither ``move_rel`` nor ``stepsize``, so calling this raises
            ``AttributeError``; left unfixed as correcting it is a behavioural
            change.
        """
        self.move_rel(direction * self.stepsize)

    def recenter(self):
        """Recenter the stage to mid-range (50 um)."""
        self.move(50)

    def INFO(self):
        """Query the controller's info string.

        Returns:
            str: The multi-line ``INFOS`` response from the controller.
        """
        return self.query(
            "INFOS",
            multiline=True,
            termination_line=" blah blah",
            timeout=.1,
        )

    def DSIO(self):
        """Query the controller's digital signal I/O state.

        Returns:
            str: The multi-line ``DSIO 1`` response from the controller.
        """
        return self.query(
            "DSIO 1",
            multiline=True,
            termination_line=" blah blah",
            timeout=.1,
        )

    def HELP(self):
        """Query the controller's help string.

        Returns:
            str: The ``HELP_`` response from the controller.
        """
        return self.query('HELP_')


if __name__ == '__main__':
    z = Piezoconcept('COM16')
