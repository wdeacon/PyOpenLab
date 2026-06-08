# -*- coding: utf-8 -*-
"""Interface module for stage controllers produced by Sigma Koki (OptoSigma).

Provides driver classes for the GSC-01, SHOT-102 and HIT multi-axis controllers.
"""
import time

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.stage import Stage
from pyopenlab.instrument.visa_instrument import VisaInstrument
from pyopenlab.utils.thread_utils import locked_action


class GSC01(SerialInstrument, Stage):
    """Driver for the Sigma Koki GSC-01 single-axis stage controller."""

    counts_per_degree = 400.
    axis_names = ('1',)
    metadata_property_names = ('position',)

    def __init__(self, address, **kwargs):
        """Open the serial connection and optionally home the stage.

        Args:
            address: Serial port address (e.g. ``'COM3'``).
            **kwargs: Optional keyword arguments. ``offsetOrigin`` (int) sets a
                homing offset; ``home_on_start`` (bool) triggers a mechanical
                home when True.
        """

        self.port_settings = dict(baudrate=9600,
                                  bytesize=8,
                                  stopbits=1,
                                  parity='N',
                                  xonxoff=True,
                                  timeout=0.5,
                                  writeTimeout=0.5,
                                  rtscts=True)
        SerialInstrument.__init__(self, address)
        self.termination_character = '\r\n'
        Stage.__init__(self)

        if 'offsetOrigin' in kwargs:
            self.offsetOrigin(kwargs['offsetOrigin'])  # 20000)

        if 'home_on_start' in list(kwargs.keys()):
            if kwargs['home_on_start']:
                self.MechanicalHome()

    def __del__(self):
        try:
            self.ser.close()
        except:
            self._logger.warn("Couldn't close GSC01")

    def wait(self):
        """Block until the controller reports it is ready (ACK3 == 'R')."""
        while self.getACK3() != 'R':
            time.sleep(0.1)

    def write_cmd(self, command, read=True, wait=False):
        """Send a serial command and read the controller's reply.

        Args:
            command: Serial command string to send to the device.
            read: If True, read and log the reply. If False, read the reply and
                warn unless it is ``'OK\\n'``.
            wait: If True, block until the controller is ready before returning.

        Returns:
            The reply string read from the controller.
        """

        self.write(command)

        if read:
            reply = self.readline()
            self._logger.debug('[%s]: %s' % (command, reply))
        else:
            reply = self.readline()
            if reply != 'OK\n':
                self._logger.warn('%s replied %s' % (command, reply))

        if wait:
            self.wait()

        return reply

    def MechanicalHome(self):
        """Detect the mechanical origin and set it as the position origin.

        Moving speed S: 500pps, F: 5000pps, R: 200ms. Running a stop command
        suspends the operation; no other commands are accepted while homing.
        """
        self.write_cmd('H:1', read=False, wait=True)

    def initializeOrigin(self):
        """
        Sets the origin to the current position.
        """
        self.write('R:1')

    def offsetOrigin(self, steps):
        """Set an offset for the homing command so the origin is not at a limit sensor.

        Effective only for the homing operation in MINI system. The value is reset
        to zero when power is turned off.

        Args:
            steps: Offset in motor steps (integer).
        """

        self.write('S:N%d' % steps)

    @locked_action
    def move(self, pos, axis=None, relative=False, wait=True):
        """Move the stage to (or by) a position in degrees.

        Args:
            pos: Target position in degrees (converted internally via
                ``counts_per_degree``).
            axis: Unused; present for interface compatibility.
            relative: If True, move relative to the current position.
            wait: If True, poll position until the target is reached or 10s elapse.

        Raises:
            ValueError: If a relative move exceeds the +/-16777214 count range.
        """
        counts = self.counts_per_degree * pos
        if relative:
            if not (-16777214 <= counts <= 16777214):
                raise ValueError('stage1 must be between -16777214 and 16777214.')

            command = 'M:W'
            if counts >= 0:
                command += '+P%d' % counts
            else:
                command += '-P%d' % -counts
        else:
            command = 'A:W'
            if counts >= 0:
                command += '+P%d' % counts
            else:
                command += '-P%d' % -counts
        self.write_cmd(command, read=False)
        self._go()

        if wait:
            t0 = time.time()
            curpos = self.get_position()[0]
            while curpos != pos and time.time() - t0 < 10:
                curpos = self.get_position()[0]
                time.sleep(0.1)

    def get_position(self, axis=None):
        """Return the current position in degrees as a single-element list.

        Args:
            axis: Unused; present for interface compatibility.

        Returns:
            A list ``[position]`` with the position in degrees.
        """
        status = self.getStatus()
        counts = status.split(',')[0]
        position = float(counts) / self.counts_per_degree
        self._logger.debug('Status: %s. Counts: %s. Position returned %g' %
                           (status, counts, position))
        return [position]

    def jog(self, direction, timeout=2):
        """Move the stage continuously at jogging speed for a set time.

        Args:
            direction: Either ``'+'`` or ``'-'``.
            timeout: Duration to jog for, in seconds.
        """

        self.write('J:1%s' % direction)
        t0 = time.time()
        self._go()
        while time.time() - t0 < timeout:
            time.sleep(0.1)
        self.decelerate()

    def _go(self):
        """
        Moves the stages. To be used internally.
        """
        self.write_cmd('G:', read=False)

    def decelerate(self):
        """
        Decelerates and stop the stages.
        """
        self.write('L:1')

    def stop(self):
        """
        Stops the stages immediately.
        """
        self.write('L:E')

    def setSpeed(self, minSpeed1, maxSpeed1, accelerationTime1):
        """Set the minimum and maximum speeds and the acceleration time.

        Args:
            minSpeed1: Between 100 and 20000, in steps of 100 [PPS].
            maxSpeed1: Between 100 and 20000, in steps of 100 [PPS].
            accelerationTime1: Between 0 and 1000 [ms].

        Raises:
            ValueError: If the speed or acceleration time is out of range.
        """
        if not (100 <= minSpeed1 <= maxSpeed1 <= 20000):
            raise ValueError('Must be 100 <= minSpeed1 <= maxSpeed1 <= 20000')

        if not (0 <= accelerationTime1 <= 1000):
            raise ValueError('Must be 00 <= accelerationTime1 <= 1000.')

        self.write('D:1S%dF%dR%d' % (minSpeed1, maxSpeed1, accelerationTime1))

    def setJogSpeed(self, speed):
        """Set the jog speed.

        Args:
            speed: Between 100 and 20000, in steps of 100 [PPS].

        Raises:
            ValueError: When ``speed`` is in the 100-20000 range.

        Note:
            The validation condition is inverted: ``if 100 < speed < 20000``
            raises for in-range values and lets out-of-range values through.
            Left unchanged to avoid a behaviour change; should likely be negated.
        """
        if 100 < speed < 20000:
            raise ValueError('Speed must be in 100-20000 range')

        self.write('S:J%d' % speed)

    def enableMotorExcitation(self, stage1=True):
        """Turn the motor on or off.

        Args:
            stage1: True to energise (hold) the motor, False to de-energise it.
        """

        self.write('C:1%d' % stage1)

    def getStatus(self):
        """Get the current status: position, command, stop and readiness flags.

        Returns:
            A reply string ``position, ACK1, ACK2, ACK3`` where:

            * ACK1: ``X`` command error, ``K`` accepted normally.
            * ACK2: ``L`` limit-sensor stop, ``K`` normal stop.
            * ACK3: ``B`` busy, ``R`` ready.
        """
        return self.write_cmd('Q:')

    def getACK3(self):
        """Return the motor readiness flag.

        Returns:
            ``'R'`` if the motor is ready, ``'B'`` if it is busy.
        """
        self.write_cmd('!:', read=False)
        return self.readline()

    def getVersion(self):
        """Return the controller's ROM version string."""
        self.write('?:V', read=False)
        return self.readline()


class SHOT(VisaInstrument, Stage):
    """Driver for the Sigma Koki SHOT-102 two-axis stage controller.

    See https://www.global-optosigma.com/en_jp/software/motorize/manual_en/SHOT-102.zip
    """
    axis_names = ('1', '2')

    def __init__(self, address, **kwargs):
        """Open the VISA connection to the controller.

        Args:
            address: VISA resource address for the controller.
            **kwargs: Accepted for interface compatibility; unused.
        """

        self.port_settings = dict(baudrate=38400,
                                  bytesize=8,
                                  stopbits=1,
                                  parity='N',
                                  xonxoff=True,
                                  timeout=0.5,
                                  writeTimeout=0.5,
                                  rtscts=True)
        VisaInstrument.__init__(self, address)
        self.termination_character = '\r\n'
        Stage.__init__(self, unit="step")

    def _rom_version(self):
        """Request the internal ROM version from the controller.

        Returns:
            The ROM version string.
        """
        return self.query("?:V")

    def _go(self, wait=True):
        """
        Moves the stages. To be used internally.
        """
        self._write_check('G:', wait=wait)

    @locked_action
    def _write_check(self, command, wait=False):
        """Send a command, check the reply and optionally wait for readiness.

        Args:
            command: Full serial command string to send.
            wait: If True, block until the controller is ready before returning.

        Returns:
            The reply string, or None if the controller replied ``'NG\\n'``.
        """
        self._logger.debug("Writing: %s" % command)
        self.write(command)
        self._logger.debug("Writing successful")
        reply = self.read()
        self._logger.debug("Read: %s" % reply)

        if reply == 'NG\n':
            self._logger.warn('%s replied %s' % (command, reply))
        else:
            if wait:
                self._wait()
            return reply

    def _wait(self):
        """Block until the controller reports it is no longer busy."""
        while self.is_busy():
            time.sleep(0.1)

    def home(self, axis="W", direction="+"):
        """Detect the machine zero and define it as the home position.

        Args:
            axis: Either ``1``, ``2`` or ``'W'`` (both axes).
            direction: Either ``'+'`` or ``'-'``.
        """

        self._write_check("H:%s%s" % (axis, direction))

    def set_origin(self, axis="W"):
        """Set the origin to the current position.

        Args:
            axis: Either ``1``, ``2`` or ``'W'`` (both axes).
        """

        self._write_check('R:' + str(axis))

    def move(self, counts, axis=1, relative=False, wait=True):
        """Move the stage by a number of motor counts.

        Args:
            counts: An integer or a tuple of two integers (positive or negative).
            axis: Either ``1``, ``2`` or ``'W'`` (both axes).
            relative: If True, move relative to the current position.
            wait: If True, block until the move completes.

        Raises:
            ValueError: If a count is outside the +/-16777214 range.
        """
        if not hasattr(counts, '__iter__'):
            counts = (counts,)
        for count in counts:
            if not (-16777214 <= count <= 16777214):
                raise ValueError('stage1 must be between -16777214 and 16777214.')

        if relative:
            command = "M:"
        else:
            command = "A:"

        if not hasattr(axis, '__iter__'):
            command += str(axis)
        else:
            command += 'W'
        for count in counts:
            if count >= 0:
                command += '+P%d' % count
            else:
                command += '-P%d' % -count

        self._write_check(command, wait=wait)
        self._go(wait=wait)

    def get_position(self, axis=None):
        """Return the position(s) in motor counts.

        Args:
            axis: A single axis, a list/tuple of axes, or None for all axes.

        Returns:
            A list of integer positions, one per requested axis.
        """
        status = self.status()
        counts = list(map(int, status.split(',')[:2]))
        if axis is None:
            axis = self.axis_names
        elif not isinstance(axis, list) and not isinstance(axis, tuple):
            axis = [axis]
        return [self.select_axis(counts, ax) for ax in axis]

    def jog(self, axis="W", direction="+", timeout=2):
        """Move the stage continuously at jogging speed for a set time.

        Args:
            axis: Either ``1``, ``2`` or ``'W'`` (both axes).
            direction: Either ``'+'`` or ``'-'``.
            timeout: Duration to jog for, in seconds.
        """

        self._write_check("J:%s%s" % (axis, direction))

        t0 = time.time()
        self._go()
        while time.time() - t0 < timeout:
            time.sleep(0.1)
        self.decelerate()

    def decelerate(self, axis="W"):
        """Decelerate and stop the stage(s).

        Args:
            axis: Either ``1``, ``2`` or ``'W'`` (both axes).
        """

        self._write_check('L:' + str(axis))

    def emergency_stop(self):
        """Stop the stages immediately."""
        self.write('L:E')

    def set_speed(self, axes, min_speed, max_speed, accel_time):
        """Change the movement speed.

        On power-up, the SHOT-102 defaults to a minimum speed (S), maximum speed
        (F) and acceleration/deceleration time (R), all set by switches 9 and 10
        on DIP Switch 1 for each speed range.

        Args:
            axes: Either ``1``, ``2`` or ``'W'`` (both axes).
            min_speed: Integer or tuple of two integers.
            max_speed: Integer or tuple of two integers.
            accel_time: Integer or tuple of two integers.

        Raises:
            ValueError: If speeds/time are out of range, or if ``axes == 'W'``
                but not all required per-axis values are supplied.
        """

        if not (1 <= min_speed <= max_speed <= 20000):
            raise ValueError('Must be 1 <= min_speed <= max_speed <= 20000')
        if not (0 <= accel_time <= 5000):
            raise ValueError('Must be 0 <= accel_time <= 5000')
        if not hasattr(min_speed, "__iter__"):
            min_speed = tuple(min_speed)
        if not hasattr(max_speed, "__iter__"):
            max_speed = tuple(max_speed)
        if not hasattr(accel_time, "__iter__"):
            accel_time = tuple(accel_time)
        if axes == "W":
            if len(min_speed) != 2 or len(min_speed) != 2 or len(min_speed) != 2:
                raise ValueError('You need to provide speeds and times for both axis')

        command = "D:%s" % axes
        for mn, mx, at in zip(min_speed, max_speed, accel_time):
            command += "S" + str(mn) + "F" + str(mx) + "R" + str(at)
        self._write_check(command)

    def on_off(self, axes, state):
        """De-energize (motor free) or energize (hold) the motor.

        Execute this to move (rotate) stages manually. Once executed, the actual
        stage position no longer matches the displayed coordinate value; perform a
        zero return to make them consistent again.

        Args:
            axes: Either ``1``, ``2`` or ``'W'`` (both axes).
            state: ``0`` (off) or ``1`` (on).
        """
        self._write_check("C:%s%s" % (axes, state))

    def status(self):
        """Check the previous command and return the controller state.

        Returns:
            A reply string ``coord_1, coord_2, ACK1, ACK2, ACK3``. Coordinates
            are 10-digit signed values (positive sign is a space). Flags:

            * ACK1: ``X`` command/parameter error, ``K`` successful command.
            * ACK2: ``L`` axis-1 e-stop, ``M`` axis-2 e-stop, ``W`` both axes
              e-stop, ``K`` normal stop.
            * ACK3: ``B`` busy, ``R`` ready.
        """
        return self.query("Q:")

    def is_busy(self):
        """Return whether the controller is currently busy.

        Returns:
            True if the controller reports busy, otherwise False.
        """
        reply = self.query("!:")

        if "B" in reply:
            return True
        else:
            return False


class HIT(SerialInstrument, Stage):
    """
    Stage controller for the many-axis HIT controller.

    https://www.global-optosigma.com/en_jp/software/motorize/manual_en/HIT_En.pdf
    """

    # TODO: interpolation commands. They set a position in the plane of two axes and jog in a curved or straight path
    # TODO: add units

    axis_names = list(map(str, list(range(8))))
    axis_LUT = dict(list(zip(list(map(str, list(range(8)))), list(range(8)))))

    def __init__(self, address, **kwargs):
        """Open the serial connection to the HIT controller.

        Args:
            address: Serial port address (e.g. ``'COM15'``).
            **kwargs: Accepted for interface compatibility; unused.
        """
        self.port_settings = dict(baudrate=38400,
                                  bytesize=8,
                                  stopbits=1,
                                  parity='N',
                                  xonxoff=True,
                                  timeout=0.5,
                                  writeTimeout=0.5,
                                  rtscts=True)
        SerialInstrument.__init__(self, address)
        self.termination_character = '\r\n'
        Stage.__init__(self, unit="step")

    def _axes_iterable(self, axes=None):
        """Convert axis names/numbers to a list of axis indices.

        Given a list of axis names or numbers (which may be mixed), returns a list
        of the corresponding axis indices using ``axis_LUT``.

        Args:
            axes: An axis name/number or list thereof (may be mixed). None means
                all axes.

        Returns:
            A list of integer axis indices.

        Raises:
            ValueError: If an axis is not recognised.
        """
        if axes is None:
            axes = self.axis_names
        if not isinstance(axes, list) and not isinstance(axes, tuple):
            axes = (axes,)
        axes_iter = []
        for ax in axes:
            if ax in list(self.axis_LUT.keys()):
                axes_iter += [self.axis_LUT[ax]]
            elif type(ax) == int:
                axes_iter += [ax]
            else:
                raise ValueError("Unrecognised axis: %s %s" % (ax, type(ax)))
        return axes_iter

    def move(self, counts, axes=None, relative=False, wait=True):
        """Move the given axes by a number of motor steps.

        Args:
            counts: Number of motor steps. If iterable, must have the same length
                as ``axes``; otherwise the same value is applied to every axis.
            axes: An axis or list of axes (None means all axes).
            relative: If True, move relative to the current position.
            wait: If True, block until the move completes.
        """
        axes = self._axes_iterable(axes)
        if not hasattr(counts, '__iter__'):
            counts = [counts] * len(axes)
        for count in counts:
            assert -134217728 < count < +134217727
        counts = list(map(int, counts))

        if relative:
            command = 'M'
        else:
            command = 'A'

        self.multi_axis_cmd(command, axes, counts, wait)

        # TODO: add checking for Stage limits using status +-LS

    def get_position(self, axes=None):
        """Return the position(s) in motor steps.

        Args:
            axes: An axis or list of axes (None means all axes).

        Returns:
            A list of integer positions; an entry is None if the value could not
            be parsed.
        """
        axes = self._axes_iterable(axes)
        all_positions = self.query("Q:").split(",")
        positions = []
        for ax in axes:
            try:
                positions += [int(all_positions[ax])]
            except ValueError:
                positions += [None]
        return positions

    def status(self, axes=None):
        """Return the overall controller status and per-axis status flags.

        Args:
            axes: An axis name/index or list thereof, or None for all axes.

        Returns:
            A tuple ``(overall_status, axes_status)`` where ``overall_status`` is
            a list of active status flags (or ``"OK"``) and ``axes_status`` is a
            dict mapping axis name to its list of flags (or ``"OK"``/None).
        """
        bit_list = ["", "DRV alarm", "Scale alarm", "Z limit", "Near", "ORG", "+LS", "-LS"]
        raw_statuses = self.query("Q:S").split(",")
        status = []
        for rs in raw_statuses:
            try:
                # Converting to 8-bit hexadecimal. https://stackoverflow.com/questions/1425493/convert-hex-to-binary
                _bin = bin(int(rs, 16))[2:].zfill(8)
                _status = []
                for bit, bit_name in zip(_bin, bit_list):
                    if bool(int(bit)):
                        _status += [bit_name]
                if len(_status) > 0:
                    status += [_status]
                else:
                    status += ["OK"]
            except ValueError:
                status += [None]
        overall_status = status[0]
        axes_status = status[1:]

        axes = self._axes_iterable(axes)
        reply = dict()
        for name, indx in zip(self.axis_names, axes):
            reply[name] = axes_status[indx]
        return overall_status, reply

    def is_moving(self, axes=None):
        """Return whether any of the given axes is currently moving.

        Args:
            axes: An axis or list of axes (None means all axes).

        Returns:
            True if any requested axis is moving, otherwise False.
        """
        axes = self._axes_iterable(axes)
        statuses = self.query("!:").split(",")
        status = []
        for ax in axes:
            status += [bool(int(statuses[ax]))]  # converting a '0' or '1' to a False or True
        return any(status)

    @locked_action
    def write_check(self, command, wait=False):
        """Send a command with error checking, locking and optional waiting.

        Args:
            command: Full serial command string to send.
            wait: If True, block until the stages have stopped before returning.

        Returns:
            The reply string, or None if the controller replied ``'NG'``.
        """
        self.write(command)

        reply = self.readline()[:-1]  # excluding the \n termination
        self._logger.debug("Reply: %s" % reply)

        if reply == 'NG':
            self._logger.warn('%s replied %s' % (command, reply))
        else:
            if wait:
                self.wait_until_stopped()
            return reply

    def multi_axis_cmd(self, command, axes, parameters, wait=False):
        """Build and send a command with parameters in the correct axis slots.

        For example, ``('H', None, 1)`` builds the command ``H:,1,,,1,,,1`` when
        the stage has three active axes at positions 1, 4 and 7.

        Args:
            command: Command code to send to the device.
            axes: An axis name/index or list thereof.
            parameters: Parameter(s) to pass. If iterable, each item maps to one
                axis; otherwise the same value is applied to every axis.
            wait: If True, block until the move completes before returning.

        Raises:
            ValueError: If ``parameters`` and ``axes`` differ in length.
        """
        axes_iter = self._axes_iterable(axes)

        if not hasattr(parameters, "__iter__"):
            parameters = [parameters] * len(axes_iter)
        if len(parameters) != len(axes_iter):
            raise ValueError("Length of axes and parameters must be the same")

        self._logger.debug("Axes: %s axes_iter: %s Parameters: %s" % (axes, axes_iter, parameters))

        argument_list = ['DUMMY'] * 8
        for ax, param in zip(axes_iter, parameters):
            argument_list[ax] = str(param)
        argument_string = ','.join(argument_list)
        argument_string = argument_string.replace('DUMMY', '')
        command += ':' + argument_string
        self._logger.debug('Writing: %s' % command)

        self.write_check(command, wait)

    def mechanical_home(self, axes=None):
        """Detect the mechanical origin for the given axes and set it as origin.

        Moving speed S: 500pps, F: 5000pps, R: 200ms. Running a stop command
        suspends the operation; no other commands are accepted while homing.

        Args:
            axes: An axis name/index or list thereof (None means all axes).
        """
        self.multi_axis_cmd('H', axes, 1, wait=True)

    def set_home(self, axes=None):
        """Set the origin of the given axes to the current position.

        Args:
            axes: An axis name/index or list thereof (None means all axes).
        """
        self.multi_axis_cmd('R', axes, 1)

    def jog(self, directions, axes=None, timeout=2):
        """Move the stage continuously at jogging speed for a set time.

        Args:
            directions: A single value or iterable of ``'+'`` or ``'-'``.
            axes: An axis name/index or list thereof (None means all axes).
            timeout: Duration to jog for, in seconds.

        Raises:
            NotImplementedError: Always; jogging requires a non-blocking
                ``write_check``, which is not yet implemented.
        """

        # TODO: make the write_check non-blocking for this to work
        raise NotImplementedError
        # self.multi_axis_cmd('J', axes, directions)
        # t0 = time.time()
        # while time.time() - t0 < timeout:
        #     time.sleep(0.1)
        # self.decelerate(axes)

    def decelerate(self, axes=None):
        """Decelerate and stop the given axes.

        Args:
            axes: An axis name/index or list thereof (None means all axes).
        """

        self.multi_axis_cmd('L', axes, 1)

    def stop_all_stages(self):
        """Stop all stages immediately."""
        self.write_check('L:E')

    def set_speed(self, axis, start_speed, max_speed, acceleration_time):
        """Set the start speed, max speed and acceleration time for an axis.

        Args:
            axis: An axis name or index (or list thereof).
            start_speed: Between 100 and 20000, in steps of 100 [PPS].
            max_speed: Between 100 and 20000, in steps of 100 [PPS].
            acceleration_time: Between 0 and 1000 [ms].

        Raises:
            ValueError: If speeds or acceleration time are out of range.
        """

        if not (1 <= start_speed <= max_speed <= 999999999):
            raise ValueError('Must be 1 <= start_speed <= max_speed <= 999999999')

        if not (1 <= acceleration_time <= 1000):
            raise ValueError('Must be 00 <= acceleration_time <= 1000.')

        axes = self._axes_iterable(axis)
        for axis in axes:
            self.write_check('D:%d,%d,%d,%d' % (axis, start_speed, max_speed, acceleration_time))

    def on_off(self, axes=None, on_off=None):
        """Turn the motor on or off for the given axes.

        Args:
            axes: An axis name/index or list thereof (None means all axes).
            on_off: True/1 (on) or False/0 (off). Defaults to on when None.
        """
        if on_off is None:
            on_off = 1

        self.multi_axis_cmd('C', axes, on_off)


if __name__ == '__main__':
    hit = HIT('COM15')
    hit._logger.setLevel("DEBUG")
    hit.show_gui()
