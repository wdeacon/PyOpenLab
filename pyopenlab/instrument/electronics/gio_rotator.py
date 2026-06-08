# -*- coding: utf-8 -*-
"""Serial driver for an Arduino-controlled rotation stage."""
import time

from pyopenlab.instrument.serial_instrument import SerialInstrument


class ArduinoRotator(SerialInstrument):
    """Rotation stage driven by an Arduino over a serial link.

    Angles are tracked in software (``_angle``); the stage is commanded in motor
    steps, converted via :attr:`STEPS_PER_REV`. Single moves are limited to
    :attr:`max_int` steps, so large rotations are split into several commands.

    Note:
        The :attr:`speed` setter clamps ``value`` into separate ``_speed`` writes,
        but then unconditionally overwrites ``_speed`` with ``int(value)``, so the
        clamp to the 1-15 range has no effect. Left unfixed (behavioral change).
    """

    STEPS_PER_REV = 16334.982528149094
    max_int = 32_767  # biggest integer the arduino can hold

    def __init__(self, port, unidirectional=False):
        """Open the serial port and initialise the rotator.

        Args:
            port: Serial port name, e.g. ``'COM5'``.
            unidirectional: If True, :meth:`move` only ever rotates in the positive
                direction, wrapping past 360 degrees rather than reversing.
        """
        self.termination_character = '\n'
        SerialInstrument.__init__(self, port)
        self.flush_input_buffer()
        self.ignore_echo = True
        self.timeout = 0.5
        time.sleep(2)  # for some reason this is necessary to change default speed
        self.speed = 15
        self._logger.setLevel('WARN')
        self._angle = 0
        self.unidirectional = unidirectional

    # def query(self, queryString, **args):
    #     return super().query(queryString, timeout=self.timeout, **args)

    @property
    def speed(self):
        """Current speed setting (1-15) last written to the Arduino."""
        return self._speed

    @speed.setter
    def speed(self, value):
        if value < 1:
            self._speed = 1
        if value > 15:
            self._speed = 15
        self._speed = int(value)
        self.write(f'S{self._speed}', ignore_echo=True)

    @property
    def angle(self):
        """Software-tracked current angle in degrees."""
        return self._angle

    @angle.setter
    def angle(self, angle):
        self.move(angle)

    def move_raw(self, steps):
        """Command a single move in motor steps and wait for the done reply.

        Args:
            steps: Signed number of motor steps to move (cast to int).

        Note:
            Polls for the Arduino's ``'1'`` acknowledgement for up to 200 seconds.
        """
        start = time.time()
        cmd = f'M{int(steps)}'
        self._logger.info('command: ' + cmd)
        self.write(cmd, ignore_echo=True)
        while time.time() - start < 200:
            reply = self.readline().strip()
            if reply == '1':
                break
            if reply:
                self._logger.info('ki-> ' + reply)
            time.sleep(0.1)

    def move_a_lot(self, steps):
        """Move a large number of steps, splitting moves exceeding :attr:`max_int`.

        Args:
            steps: Signed total number of steps to move. Moves larger than the
                Arduino's integer limit are issued as several sequential commands,
                so the rotation may be momentarily discontinuous at the seams.
        """
        if steps == 0:
            return

        sign = (1, -1)[steps < 0]
        steps = abs(steps)

        movements = 0
        if steps > self.max_int:
            movements = steps // self.max_int
            steps = steps % self.max_int

        for movement in range(movements):
            self._logger.info('starting new command, rotation may be discontinuous')
            self.move_raw(sign * self.max_int)

        self.move_raw(sign * steps)

    def move_rel(self, degrees):
        """Rotate by a relative angle and update the tracked angle.

        Args:
            degrees: Relative rotation in degrees; positive is clockwise.
        """
        self._logger.info(f'moving {degrees} degrees')
        self.move_a_lot(int(-degrees * self.STEPS_PER_REV / 360))
        self._angle += degrees

    def move(self, degree):
        """Move to an absolute angle.

        Args:
            degree: Target absolute angle in degrees. In unidirectional mode, a
                target behind the current angle is reached by adding 360 degrees so
                the stage only ever turns one way.
        """
        if self.angle > degree and self.unidirectional:
            degree += 360
        self.move_rel(degree - self.angle)

    def home(self):
        """Rotate forward to the 0-degree position (no-op if already there)."""
        if self.angle == 0.:
            return
        self.move_rel(360 - self.angle)

    def calibrate(self, rotations: int = 5):
        """Recalibrate :attr:`STEPS_PER_REV` from a measured over/undershoot.

        Spins the stage a known number of rotations, then prompts the user for the
        observed over/undershoot in degrees and adjusts the steps-per-revolution
        constant accordingly.

        Args:
            rotations: Number of full clockwise rotations to perform.
        """
        print(f'rotating clockwise {rotations} rotations')
        self.speed = 15
        self.move_rel(rotations * 360)
        overshoot = float(
            input('''How far did it over/undershoot
                          (in degrees)?'''))

        self.STEPS_PER_REV = self.STEPS_PER_REV * (rotations) / (rotations + overshoot / 360)
        print(f'steps per rev = {self.STEPS_PER_REV} ')


if __name__ == '__main__':
    ard = ArduinoRotator('COM5')
    ard._logger.setLevel('INFO')
