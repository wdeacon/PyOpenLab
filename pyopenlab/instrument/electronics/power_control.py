# -*- coding: utf-8 -*-
"""Closed-loop laser power control via a calibrated attenuator and power meter."""

import os
import time

import numpy as np
from qtpy import QtWidgets
from qtpy import uic
from scipy import interpolate

from pyopenlab import datafile
from pyopenlab.datafile import sort_by_timestamp
from pyopenlab.experiment.gui import run_function_modally
from pyopenlab.instrument import Instrument
from pyopenlab.instrument.electronics.aom import AOM as Aom
from pyopenlab.instrument.electronics.power_meter import PowerMeter
from pyopenlab.instrument.electronics.thorlabs_pm100 import ThorlabsPowermeter
from pyopenlab.instrument.stage import Stage
from pyopenlab.instrument.stage.Thorlabs_ELL8K import Thorlabs_ELL8K as RStage
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.notified_property import DumbNotifiedProperty
from pyopenlab.utils.notified_property import NotifiedProperty
from pyopenlab.utils.notified_property import register_for_property_changes


def isMonotonic(A):
    """Return True if sequence ``A`` is monotonic (non-increasing or non-decreasing).

    Args:
        A: Indexable sequence of comparable values.

    Returns:
        bool: True if ``A`` never changes direction.
    """
    return (all(A[i] <= A[i + 1] for i in range(len(A) - 1)) or
            all(A[i] >= A[i + 1] for i in range(len(A) - 1)))


class PowerControl(Instrument):
    """Set laser power via a calibrated continuous attenuator.

    The ``power_controller`` is anything with a continuous input parameter (a
    rotation-stage filter wheel or an AOM); a calibration maps that parameter to
    the power read by an attached power meter, so power can be set directly.
    """
    calibrate_points = DumbNotifiedProperty(25)

    def __init__(self,
                 power_controller,
                 power_meter,
                 before_calibration_func=None,
                 after_calibration_func=None,
                 calibration_points=25,
                 title='power control',
                 move_range=(0, 1)):
        """Set up the controller, meter and parameter range.

        Args:
            power_controller: The attenuator (rotation stage or AOM) whose
                continuous parameter sets the power.
            power_meter: A :class:`PowerMeter` used to read the power.
            before_calibration_func: Optional callable run before a calibration,
                whose return value is passed to ``after_calibration_func``.
            after_calibration_func: Optional callable run after a calibration.
            calibration_points: Number of points to sample during calibration.
            title: Name used for the calibration data group and config keys.
            move_range: ``(min, max)`` parameter range for generic controllers
                (overridden for known rotation stages and AOMs).
        """
        super().__init__()
        self.pc = power_controller
        self.pometer = power_meter
        self.calibration_points = calibration_points
        self.title = title
        self.before_calibration_func = before_calibration_func
        self.after_calibration_func = after_calibration_func
        # assert isinstance(power_controller, (Aom, Stage)), \
        #     ('power_controller must be AOM or Stage')
        assert isinstance(power_meter, PowerMeter), \
            ('Power meter have power_meter.PowerMeter base class')

        if isinstance(self.pc, RStage):
            self.min_param, self.max_param = 0, 360

        elif isinstance(self.pc, Aom):
            self.min_param, self.max_param = 0, 1
        else:
            self.min_param, self.max_param = move_range
        self.maxpower = None
        self.minpower = None
        self.update_power_calibration()

        if isinstance(self.pc, Stage):
            self.set_param = self.pc.move
            self.get_param = self.pc.get_position
        if isinstance(self.pc, Aom):
            self.set_param = self.pc.Power
            self.get_param = self.pc.Get_Power

    @property
    def param(self):
        """The attenuator's current control parameter (angle or AOM level)."""
        return self.get_param()

    @param.setter
    def param(self, value):
        self.set_param(value)

    @property
    def mid_param(self):
        """float: The midpoint of the parameter range."""
        return (self.max_param - self.min_param) / 2

    @property
    def points(self):
        """ndarray: The parameter values sampled during calibration.

        Spaced logarithmically for rotation stages and linearly for AOMs.
        """
        if isinstance(self.pc, RStage):
            if self.min_param < self.max_param:
                return np.logspace(0, np.log10(self.max_param - self.min_param),
                                   self.calibration_points) + self.min_param
            return self.min_param - np.logspace(0, np.log10(self.min_param - self.max_param),
                                                self.calibration_points)
        else:  # isinstance(self.pc, Aom):
            return np.linspace(self.min_param,
                               self.max_param,
                               num=self.calibration_points,
                               endpoint=True)

    def calibrate_power(self,
                        fw_min=None,
                        fw_max=None,
                        num_points=None,
                        update_progress=lambda p: p):
        """Sweep the attenuator and record power at each point.

        Steps through :attr:`points`, reads the power meter at each, saves the
        sweep to a new data group, recentres the attenuator and refreshes the
        calibration.

        Args:
            fw_min: Optional override for the minimum parameter value.
            fw_max: Optional override for the maximum parameter value.
            num_points: Optional override for the number of calibration points.
            update_progress: Callback invoked with the point index for progress
                reporting.
        """
        if self.before_calibration_func is not None:
            state = self.before_calibration_func()
        attrs = {}

        if fw_min is not None:
            self.min_param = fw_min
        if fw_max is not None:
            self.max_param = fw_max
        if num_points is not None:
            self.calibration_points = num_points

        if isinstance(self.pc, RStage):
            attrs['Angles'] = self.points
        if isinstance(self.pc, Aom):
            attrs['Voltages'] = self.points

        attrs['x_axis'] = self.points
        attrs['parameters'] = self.points
        attrs['wavelengths'] = self.points

        powers = []

        for i, point in enumerate(self.points):
            self.param = point
            time.sleep(.2)
            powers.append(self.pometer.power)
            update_progress(i)

        group = self.create_data_group(self.title + '_%d')
        group.create_dataset(name='powers', data=powers, attrs=attrs)

        self.param = self.mid_param
        self.update_power_calibration()
        if self.after_calibration_func is not None:
            self.after_calibration_func(*state)

    def update_power_calibration(self, specific_calibration=None, laser=None):
        """Load a power calibration into memory and into the config file.

        Args:
            specific_calibration: Exact name of the calibration data group to
                load. If ``None``, the most recent matching calibration is used,
                falling back to the config file.
            laser: Unused; retained for backwards compatibility.
        """

        initial = datafile._use_current_group
        datafile._use_current_group = False
        search_in = self.get_root_data_folder()
        datafile._use_current_group = initial
        if specific_calibration is not None:
            try:
                power_calibration_group = search_in[specific_calibration]
                pc = power_calibration_group['powers']
                self.power_calibration = {'powers': pc[()], 'parameters': pc.attrs['parameters']}
                if isMonotonic(self.power_calibration['powers']):
                    self.update_config('parameters_' + self.title, pc.attrs['parameters'])
                    self.update_config('powers_' + self.title, pc[()])
                else:
                    print('power curve isn\'t monotonic, not saving to config file')

            except ValueError:
                print('This calibration doesn\'t exist!')
                return
        else:

            candidates = [
                group for name, group in sort_by_timestamp(search_in)  # return key val pairs
                if '_'.join(name.split('_')[:-1]) == self.title]
            if candidates:
                power_calibration_group = candidates[-1]
                pc = power_calibration_group['powers']
                self.power_calibration = {'powers': pc[()], 'parameters': pc.attrs['parameters']}
                if isMonotonic(self.power_calibration['powers']):
                    self.update_config('parameters_' + self.title, pc.attrs['parameters'])
                    self.update_config('powers_' + self.title, pc[()])
                else:
                    print('power curve isn\'t monotonic, not saving to config file')
            else:
                if len(self.config_file) > 0:
                    self.power_calibration = {
                        '_'.join(n.split('_')[:-1]): f
                        for n, f in self.config_file.items()
                        if n.endswith(self.title)}
                    print(
                        f'No power calibration in current file, using inaccurate configuration ({self.title})'
                    )
                else:
                    print(f'No power calibration found ({self.title})')

    @property
    def power(self):
        """The measured power; setting it drives the attenuator to that power."""
        return self.pometer.power

    @power.setter
    def power(self, value):
        self._power = value
        self.param = self.power_to_param(value)

    def power_to_param(self, power):
        """Convert a target power to the attenuator parameter via the calibration.

        Args:
            power: Desired power.

        Returns:
            The interpolated attenuator parameter for ``power``.
        """
        params = self.power_calibration['parameters']
        powers = np.array(self.power_calibration['powers'])
        curve = interpolate.interp1d(powers, params, kind='cubic')
        return curve(power)

    def param_to_power(self, param):
        """Convert an attenuator parameter to power via the calibration.

        Args:
            param: Attenuator parameter value.

        Returns:
            The interpolated power for ``param``.
        """
        params = self.power_calibration['parameters']
        powers = np.array(self.power_calibration['powers'])
        curve = interpolate.interp1d(params, powers, kind='cubic')
        return curve(param)

    def get_qt_ui(self):
        """Return the Qt control widget for this power controller.

        Returns:
            PowerControl_UI: A widget bound to this instrument.
        """
        return PowerControl_UI(self)


class PowerControl_UI(QtWidgets.QWidget, UiTools):
    """Qt control panel for a :class:`PowerControl` instrument."""

    def __init__(self, PC):
        """Build the UI and bind it to the power controller.

        Args:
            PC: The :class:`PowerControl` instance to control.
        """
        super(PowerControl_UI, self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'power_control.ui'), self)
        self.PC = PC
        self.auto_connect_by_name(controlled_object=self.PC)
        self._power_doubleSpinBox.valueChanged.connect(self._power_changed)
        self.title_label.setText(self.PC.title)

    def _power_changed(self, new):
        self.PC.power = new

    def calibrate_power_gui(self):
        """Run a power calibration with a modal progress dialog."""
        run_function_modally(self.PC.calibrate_power, progress_maximum=len(self.PC.points))


if __name__ == '__main__':

    from pyopenlab import datafile
    from pyopenlab.instrument.electronics.thorlabs_pm100 import ThorlabsPowermeter
    from pyopenlab.instrument.shutter.BX51_uniblitz import Uniblitz
    from pyopenlab.instrument.shutter.thorlabs_sc10 import ThorLabsSC10

    filter_wheel = RStage('COM8')
    powermeter = ThorlabsPowermeter('USB0::0x1313::0x807B::201029132::0::INSTR')
    power_control = PowerControl(filter_wheel, powermeter)
    power_control.show_gui(False)
