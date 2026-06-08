# -*- coding: utf-8 -*-
"""Power-calibration helpers pairing a power meter with a rotation/filter stage.

Provides :class:`WheelOfPower`, a thin wrapper for moving to a target power, and
:class:`PowerWheelMixin`, a reusable calibration mixin for power-controlling
instruments.
"""
from collections import deque
import os
import threading
import time

import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import minimize

from pyopenlab.experiment.gui import run_function_modally


class WheelOfPower(object):
    """Wrapper combining a filter wheel and a power meter to move to a set power.

    Builds an interpolated lookup of stage angle versus measured power so the
    stage can be driven to a requested power level.
    """

    def __init__(self, power_meter, rotation_stage):
        """Store the instruments and initialise the rolling power history.

        Args:
            power_meter: Power meter instrument exposing ``average_power``.
            rotation_stage: Rotation/filter stage exposing ``move``.
        """
        self.power_meter = power_meter
        self.rotation_stage = rotation_stage
        self.abort_deque = False
        self.deque_time = 1.0
        self.deque_length = 100
        self.history_deque = deque(maxlen=self.deque_length)

    def calibrate(self, start=0, stop=360, steps=360):
        """Sweep the stage and build an interpolated power-versus-angle table.

        Args:
            start: First stage position to measure.
            stop: Last stage position to measure.
            steps: Number of measurement points across the sweep.
        """
        stage_positions = np.linspace(start, stop, steps)
        powers = []
        for position in stage_positions:
            self.rotation_stage.move(position)
            powers.append(self.power_meter.average_power)
        powers = np.array(powers)
        interp_function = interp1d(stage_positions, powers)
        new_stage_positions = np.linspace(start, stop, steps * 100)
        new_powers = interp_function(new_stage_positions)
        self.powers = new_powers
        self.stage_position = new_stage_positions

    def power_to_pos(self, power):
        """Return the stage position(s) whose calibrated power is closest to ``power``.

        Args:
            power: Target power level.

        Returns:
            The stage position(s) from the interpolated table nearest to ``power``.
        """
        return self.stage_position[self.powers == self.find_nearest(self.powers, power)]

    def find_nearest(self, array, value):
        """Return the element of ``array`` closest to ``value``.

        Args:
            array: Array to search.
            value: Target value.

        Returns:
            The array element with the smallest absolute difference from ``value``.
        """
        return array[np.abs(array - value).argmin()]

    def move_to_power(self, power):
        """Move the rotation stage to the position giving the requested power.

        Args:
            power: Target power level.
        """
        pos = self.power_to_pos(power)
        self.rotation_stage.move(pos)

    def update_deque(self):
        """Continuously average power readings into the history deque until aborted.

        Each iteration averages readings over ``deque_time`` seconds and appends
        the mean to ``history_deque``. Set ``abort_deque`` True to stop the loop.
        """
        running = True
        while running:
            t0 = time.time()
            current_powers = []
            while (time.time() - t0) < self.deque_time:
                current_powers.append(self.power_meter.average_power)
            self.history_deque.append(np.average(current_powers))
            if self.abort_deque == True:
                running = False
        self.abort_deque = False

    def start_deque_thread(self):
        """Start a background thread running :meth:`update_deque`."""
        self.deque_thread = threading.Thread(target=self.update_deque)
        self.deque_thread.start()

    def clear_deque_thread(self):
        """Reset the power history deque to an empty deque.

        Note:
            Despite the name, this only clears ``history_deque``; it does not stop
            the running thread (use ``abort_deque`` for that).
        """
        self.history_deque = deque(maxlen=self.deque_length)


class PowerWheelMixin(object):
    """
    General mixin to add calibration functions to an instrument that controls power. The general calibration is done by
    providing interpolation functions to the measured power dependency.

    The user must implement the raw_power property.
    Optionally, the prepare_calibration gives some flexibility in choosing the interpolation region.
    """

    def __init__(self):
        """Initialise identity calibration functions and empty calibration state."""
        super(PowerWheelMixin, self).__init__()
        self.cal_to_raw = lambda x: x
        self.raw_to_cal = lambda x: x
        self.calibration = None
        self._raw_calibration = None
        self._raw_min = 0
        self._raw_max = 1

    @property
    def raw_power(self):
        """Raw, uncalibrated power setting. Must be implemented by subclasses.

        Raises:
            NotImplementedError: Always, until overridden by a subclass.
        """
        raise NotImplementedError

    @raw_power.setter
    def raw_power(self, value):
        raise NotImplementedError

    def prepare_calibration(self, calibration):
        """Optionally process the raw calibration before interpolation.

        Useful when the calibration is not monotonic (which would make one of the
        interpolations multivalued). The default implementation is a no-op.

        Args:
            calibration: The raw calibration array.

        Returns:
            The (optionally processed) calibration array.
        """
        return calibration

    def _calibration_functions(self, calibration=None):
        """Build the cal-to-raw and raw-to-cal interpolation functions.

        Args:
            calibration: A ``[raw, cal]`` array. Defaults to ``self.calibration``.
        """
        if calibration is None:
            calibration = self.calibration
        self.cal_to_raw = interp1d(calibration[1], calibration[0])
        self.raw_to_cal = interp1d(calibration[0], calibration[1])

    def recalibrate(self, power_meter, points=3):
        """Rescale the existing calibration by a single multiplicative factor.

        Selects a few random points and finds the factor that best matches the
        calibration to freshly measured values, assuming the only change is a
        multiplicative scaling.

        Args:
            power_meter: Instrument instance with a ``power`` property.
            points: Number of points to check.
        """
        assert self.calibration is not None

        old_calibration = np.copy(self.calibration)

        rand_indices = np.random.choice(old_calibration.shape[1], points)
        raw_vals = old_calibration[0, rand_indices]
        old_cal = old_calibration[1, rand_indices]
        run_function_modally(self._recalibrate, points, power_meter, raw_vals, old_cal)

    def _recalibrate(self, power_meter, raw_vals, old_cal, update_progress=lambda p: p):
        new_cal = []
        for idx, raw in enumerate(raw_vals):
            update_progress(idx)
            self.raw_power = raw
            new_cal += [power_meter.power]

        def minimise(params):
            return np.sum(np.abs((old_cal * params[0]) - new_cal))

        results = minimize(minimise, np.array([1]))

        self.calibration[1] *= results.x[0]
        self._calibration_functions()

    def calibrate(self, power_meter, points=51, min_power=None, max_power=None):
        """
        General calibration procedure. Iterates over 'raw_powers', and measures the actual powers using a powermeter

        :param power_meter: powermeter instrument with 'power' property
        :param points: int. Number of interpolation points
        :param min_power: float. minimum value of raw_power
        :param max_power: float. maximum value of raw_power
        :return:
        """
        if min_power is None:
            min_power = self._raw_min
        if max_power is None:
            max_power = self._raw_max

        raw_powers = np.linspace(min_power, max_power, points)
        run_function_modally(self._calibrate, points, power_meter, raw_powers)

    def _calibrate(self, power_meter, raw_powers, update_progress=lambda p: p):
        powers = np.array([])
        for idx, raw in enumerate(raw_powers):
            update_progress(idx)
            self.raw_power = raw
            powers = np.append(powers, power_meter.power)
        self._raw_calibration = np.array([raw_powers, powers])
        self.calibration = self.prepare_calibration(self._raw_calibration)
        self._calibration_functions()

    def save_calibration(self, filename=None):
        """
        Save calibration to a .txt using numpy
        :param filename: str
        :return:
        """
        if filename is None:
            filename = os.path.dirname(os.path.abspath(__file__)) + '/powerwheel_calibration.txt'
        np.savetxt(filename, self.calibration)

    def load_calibration(self, filename=None, power_meter=None):
        """
        Load a numpy-saved .txt

        :param filename: str
        :param power_meter: powermeter instrument with a 'power' attribute. If given, PowerWheel will recalibrate
        :return:
        """
        if filename is None:
            filename = os.path.dirname(os.path.abspath(__file__)) + '/powerwheel_calibration.txt'
        self.calibration = np.loadtxt(filename)
        if power_meter is not None:
            self.recalibrate(power_meter)
        self._calibration_functions()

    @property
    def power(self):
        return self.raw_to_cal(self.raw_power)

    @power.setter
    def power(self, value):
        self.raw_power = self.cal_to_raw(value)
