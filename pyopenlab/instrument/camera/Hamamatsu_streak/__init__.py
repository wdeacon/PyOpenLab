# -*- coding: utf-8 -*-
"""Camera driver and Qt control widget for the Hamamatsu streak camera.

Builds on :class:`StreakSdk` (the RemoteEx TCP wrapper) and the pyopenlab scaled-ROI
camera mixin to provide snapshotting and a GUI.
"""
import os
from weakref import WeakSet

from pyopenlab.instrument.camera.camera_scaled_roi import CameraRoiScale
from pyopenlab.instrument.camera.camera_scaled_roi import DisplayWidgetRoiScale
from pyopenlab.instrument.camera.Hamamatsu_streak.streak_sdk import StreakError
from pyopenlab.instrument.camera.Hamamatsu_streak.streak_sdk import StreakSdk
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic


class Streak(StreakSdk, CameraRoiScale):
    """Hamamatsu streak camera combining the RemoteEx SDK with scaled-ROI camera behaviour."""

    def __init__(self, *args, **kwargs):
        super(Streak, self).__init__(*args, **kwargs)

    def get_control_widget(self):
        """Return a Qt control widget for this camera."""
        return StreakUI(self)

    def get_preview_widget(self):
        """Create, register and return a new scaled-ROI image preview widget."""
        self._logger.debug('Getting preview widget')
        if self._preview_widgets is None:
            self._preview_widgets = WeakSet()
        new_widget = DisplayWidgetRoiScale()
        self._preview_widgets.add(new_widget)
        return new_widget

    def raw_snapshot(self):
        """Capture a single image and attach metadata.

        Returns:
            tuple: ``(True, image_with_metadata)`` on success. On failure the exception is
            logged and ``None`` is returned implicitly.
        """
        try:
            image = self.capture()
            return True, self.bundle_metadata(image)
        except Exception as e:
            self._logger.warn("Couldn't Capture because %s" % e)


class StreakUI(QtWidgets.QWidget):
    """Qt control panel for a :class:`Streak` camera, loaded from ``Streak.ui``."""

    ImageUpdated = QtCore.Signal()

    def __init__(self, streak):
        super(StreakUI, self).__init__()

        self.Streak = streak
        uic.loadUi((os.path.dirname(__file__) + '/Streak.ui'), self)

        self.comboBoxGateMode.activated.connect(self.gate_mode)
        self.comboBoxReadMode.activated.connect(self.read_mode)
        self.comboBoxShutter.activated.connect(self.shutter)
        self.comboBoxTrigMode.activated.connect(self.trigger)
        self.spinBox_MCPGain.valueChanged.connect(self.mcp_gain)
        self.lineEditTimeRange.returnPressed.connect(self.time_range)
        self.comboBoxTimeUnit.activated.connect(self.time_range)
        self.pushButtonLess.clicked.connect(lambda: self.time_range('-'))
        self.pushButtonMore.clicked.connect(lambda: self.time_range('+'))

        self.pushButtonCapture.clicked.connect(
            lambda: self.Streak.raw_image(update_latest_frame=True))

    def gate_mode(self):
        """Apply the gate mode selected in the combo box to the camera."""
        mode = str(self.comboBoxGateMode.currentText())
        self.Streak.set_parameter('Devices', 'TD', 'Gate Mode', mode)

    def read_mode(self):
        """Apply the read mode selected in the combo box to the camera."""
        mode = str(self.comboBoxReadMode.currentText())
        self.Streak.set_parameter('Devices', 'TD', 'Mode', mode)

    def shutter(self):
        """Apply the shutter setting selected in the combo box to the camera."""
        mode = str(self.comboBoxShutter.currentText())
        self.Streak.set_parameter('Devices', 'TD', 'Shutter', mode)

    def trigger(self):
        """Apply the trigger mode selected in the combo box to the camera."""
        mode = str(self.comboBoxTrigMode.currentText())
        self.Streak.set_parameter('Devices', 'TD', 'Trig. Mode', mode)

    def mcp_gain(self):
        """Apply the MCP gain from the spin box to the camera."""
        gain = int(self.spinBox_MCPGain.value())
        self.Streak.set_parameter('Devices', 'TD', 'MCP Gain', gain)

    def time_range(self, direction=None):
        """Set the streak time range, optionally stepping up or down the allowed values.

        With no ``direction`` the nearest allowed value to the entered number is applied.
        ``'+'``/``'-'`` step to the next/previous allowed value, rolling over into the
        adjacent time unit (ns/us/ms) at the ends of each range.

        Args:
            direction (str, optional): ``'+'`` to increase, ``'-'`` to decrease, or
                ``None`` to snap the typed value to the nearest allowed setting.

        Note:
            ``direction is '+'`` / ``direction is '-'`` compare strings with ``is`` rather
            than ``==``; this happens to work via interning of the literals passed in but
            relies on a CPython implementation detail (emits a SyntaxWarning on modern
            Python). Left unchanged to preserve behaviour.
        """
        allowed_times = {
            'ns': [5, 10, 20, 50, 100, 200, 500],
            'us': [1, 2, 5, 10, 20, 50, 100, 200, 500],
            'ms': [1]}
        unit = str(self.comboBoxTimeUnit.currentText())
        given_number = int(self.lineEditTimeRange.text())

        if direction is '+':
            if not (unit == 'ms' and given_number == 1):
                next_unit = str(unit)
                if given_number != 500:
                    next_number = allowed_times[unit][allowed_times[unit].index(given_number) + 1]
                else:
                    next_number = 1
                    if unit == 'ns':
                        self.comboBoxTimeUnit.setCurrentIndex(1)
                        next_unit = 'us'
                    elif unit == 'us':
                        self.comboBoxTimeUnit.setCurrentIndex(2)
                        next_unit = 'ms'
                self.lineEditTimeRange.setText(str(next_number))
                unit = str(next_unit)
            else:
                self.Streak._logger.info('Tried increasing the maximum time range')
                return
        elif direction is '-':
            if not (unit == 'ns' and given_number == 5):
                next_unit = str(unit)
                if given_number != 1:
                    next_number = allowed_times[unit][allowed_times[unit].index(given_number) - 1]
                else:
                    next_number = 500
                    if unit == 'ms':
                        self.comboBoxTimeUnit.setCurrentIndex(1)
                        next_unit = 'us'
                    elif unit == 'us':
                        self.comboBoxTimeUnit.setCurrentIndex(0)
                        next_unit = 'ns'
                self.lineEditTimeRange.setText(str(next_number))
                unit = str(next_unit)
            else:
                self.Streak._logger.info('Tried decreasing the minimum time range')
                return
        else:
            next_number = min(allowed_times[unit], key=lambda x: abs(x - given_number))
            self.lineEditTimeRange.setText(str(next_number))

        # Some camera models don't give you direct access to the time range, but rather you preset a finite number of
        # settings that you then switch between
        try:
            self.Streak.set_parameter('Devices', 'TD', 'Time Range', str(next_number) + ' ' + unit)
        except StreakError:
            self.Streak.set_parameter('Devices', 'TD', 'Time Range', str(next_number))
