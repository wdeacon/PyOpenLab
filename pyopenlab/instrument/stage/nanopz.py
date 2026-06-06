# -*- coding: utf-8 -*-
"""Driver for the Newport NanoPZ piezo motion actuator."""

import time

import serial

import pyopenlab.instrument.serial_instrument as si
from pyopenlab.instrument.stage import Stage

ERROR_CODE = {
    '0': 'No error',
    '2': 'Driver fault (thermal shut down)',
    '6': 'Unknown command',
    '7': 'Parameter out of range',
    '8': 'No motor connected',
    '26': 'Positive software limit detected',
    '27': 'Negative software limit detected',
    '38': 'Command parameter missing',
    '50': 'Communication overflow',
    '213': 'Motor not enabled',
    '214': 'Invalid axis',
    '226': 'Command not allowed during motion',
    '227': 'Command not allowed',
    '240': 'Jog wheel over speed'}


class NanoPZ(si.SerialInstrument, Stage):
    """Newport NanoPZ piezo actuator controller over serial.

    Note:
        The default ``controllerNOM`` is the string ``"1"``, but ``__init__``
        tests ``controllerNOM < 10`` to decide on zero-padding. Comparing a str
        to an int raises ``TypeError`` on Python 3, so the default value must
        be overridden with an int to construct the object. Left unfixed as it
        requires a behavioural decision beyond a surgical docstring change.
    """

    def __init__(self, port=None, controllerNOM="1"):
        """Connect to the controller and enable the motor.

        Args:
            port (str): Serial port the controller is on.
            controllerNOM: Controller number; values below 10 are zero-padded
                to two digits (e.g. ``2`` becomes ``"02"``).
        """
        self.port_settings = {
            'baudrate': 19200,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'timeout': 1,  #wait at most one second for a response
            'writeTimeout': 1,  #similarly, fail if writing takes >1s
            'xonxoff': True,
            'rtscts': False,
            'dsrdtr': False,}
        si.SerialInstrument.__init__(self, port=port)
        self.termination_character = '\r'
        self.stepsize = 10
        if controllerNOM < 10:
            controllerNOM = "0%s" % controllerNOM
        self.controllerNOM = controllerNOM
        self.motor_on()

    def _send_command(self, msg):
        """Write a command to the controller, prefixed with its number.

        Args:
            msg (str): Command body without the leading controller number.
        """
        self.ser.write('{0}{1}'.format(self.controllerNOM, msg))

    def _readerror(self):
        """Query and return the controller's current error, if any.

        Note:
            ``error`` is parsed as a string but compared against the integer
            ``0`` (``if error != 0``), so the comparison is always True and a
            description is returned even when the error code is ``"0"`` (no
            error). Left unfixed as it is a behavioural bug beyond a surgical
            docstring change.

        Returns:
            str: The error description, or None when no command is matched.
        """
        self.ser.write('{0}TE?'.format(self.controllerNOM))
        a = self.ser.readline()
        b = a.split(' ')[1]
        error = b.split('\r')[0]

        if error != 0:
            self._logger.warn('%s' % (ERROR_CODE[error]))
            return ERROR_CODE[error]

    def getHardwareStatus(self):
        """Query the hardware status (``PH?``).

        Returns:
            str: Raw status line read from the controller.
        """
        self._send_command('PH?')
        status = self.ser.readline()
        return status

    def getControllerStatus(self):
        """Query the controller status (``TS?``).

        Returns:
            str: Raw status line read from the controller.
        """
        self._send_command('TS?')
        status = self.ser.readline()
        return status

    def stop_motion(self):
        """Stop any motion in progress (``ST``)."""
        self._send_command('ST')

    def move(self, pos, relative=True):
        """Move the actuator.

        Only relative moves are supported; an absolute move logs a warning and
        does nothing.

        Args:
            pos: Number of steps to move (relative).
            relative (bool): Must be True; False is unsupported.
        """
        if relative:
            self._send_command("PR{0}".format(pos))
        else:
            self._logger.warn('NanoPZ does not have absolute moving')

    # def move_rel(self,value):
    #     self.write("{0}PR{1}".format(self.controllerNOM, value))

    def move_step(self, direction):
        """Move by one configured step in the given direction.

        Note:
            This calls ``self.move_rel(...)``, which does not exist on this
            class (the only ``move_rel`` is commented out), so the method
            raises ``AttributeError``. The intended call is likely
            ``self.move(direction * self.stepsize)``. Left unfixed as a
            behavioural change is out of scope for this docstring pass.

        Args:
            direction: Sign/magnitude multiplier applied to ``stepsize``.
        """
        self.move_rel(direction * self.stepsize)

    def motor_on(self):
        """Enable the motor (``MO``)."""
        self._send_command("MO")

    def get_position(self, axis=None):
        """Query the current position (``TP?``).

        Note:
            The slice ``[len("{0}TP?") - 1:]`` measures the unformatted literal
            ``"{0}TP?"`` (6 characters) rather than the controller number plus
            command, so it strips a fixed 5 characters regardless of the actual
            prefix length. Left unfixed as correcting it is a behavioural
            change.

        Args:
            axis: Unused; present for Stage interface compatibility.

        Returns:
            str: Position portion of the controller's reply.
        """
        return self.query("{0}TP?".format(self.controllerNOM))[len("{0}TP?") - 1:]

    def set_zero(self):
        """Define the current position as the origin (``OR``)."""
        self._send_command("OR")

    def lower_limit(self, value):
        """Set the negative software travel limit (``SL``).

        Args:
            value: Limit value; must be negative. A non-negative value prints
                the current limit instead of setting it.
        """
        if value < 0:
            self._send_command("SL{0}".format(value))
        else:
            print("The lower Limit must be less than 0, current lower limit = ",
                  self.query("{0}SL?".format(self.controllerNOM)))

    def upper_limit(self, value):
        """Set the positive software travel limit (``SR``).

        Args:
            value: Limit value; must be positive. A non-positive value prints
                the current limit instead of setting it.
        """
        if value > 0:
            self._send_command("SR{0}".format(value))
        else:
            print("The upper Limit must be greater than 0, current upper limit = ",
                  self.query("{0}SR?".format(self.controllerNOM)))


if __name__ == '__main__':
    teststage = NanoPZ(port="COM25")
