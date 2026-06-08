# -*- coding: utf-8 -*-
"""
Collection of modular GUIs that can be used for creating SLM patterns.

When a new SLM class is called, the GUI created adds any of the following to a pyqtgraph.DockArea by importing them by
name (so the naming of these classes is not arbitrary).
"""
from __future__ import division

from builtins import str
import os

import numpy as np

from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic


class BaseUi(QtWidgets.QWidget, UiTools):
    """Base widget for SLM option GUIs that loads its ``.ui`` file by name and wires up signals."""

    def __init__(self, slm_gui, name):
        """Load the ``ui_<name>.ui`` layout and connect its signals.

        Args:
            slm_gui (SlmUi): The parent SLM control GUI.
            name (str): Option name, used to locate the ``ui_<name>.ui`` file.
        """
        super(BaseUi, self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'ui_%s.ui' % name), self)
        self.slm_gui = slm_gui
        self._connect()

    def _connect(self):
        """Connect widget signals to slots. Subclasses override this; the base is a no-op."""
        return

    def get_params(self):
        """Return the parameters to pass to the pattern generator of the same name as the class.

        Returns:
            tuple: Positional arguments for the matching pattern generator.

        Raises:
            NotImplementedError: Always; subclasses must override this method.
        """
        raise NotImplementedError


class constantUi(BaseUi):
    """GUI for the :func:`constant` pattern generator: a uniform phase offset."""

    def __init__(self, slm_gui):
        super(constantUi, self).__init__(slm_gui, 'constant')

    def _connect(self):
        self.offset_slider.valueChanged.connect(self.update_offset_lineedit)
        self.offset_lineEdit.returnPressed.connect(self.update_offset_slider)
        self.offset_slider.valueChanged.connect(self.slm_gui.make)

    def update_offset_lineedit(self):
        """Update the offset line edit from the offset slider position."""
        steps = self.offset_slider.value()
        value = 2 * steps / 100.
        self.offset_lineEdit.setText('%g' % value)

    def update_offset_slider(self):
        """Update the offset slider from the offset line edit."""
        value = float(self.offset_lineEdit.text())
        steps = 100 * value / 2.
        self.offset_slider.setValue(steps)

    def get_params(self):
        """Return the constant phase offset in radians.

        Returns:
            tuple: ``(offset,)`` where ``offset`` is in radians.
        """
        return np.pi * float(self.offset_lineEdit.text()),


class calibration_responsivenessUi(BaseUi):
    """GUI for the :func:`calibration_responsiveness` pattern generator."""

    def __init__(self, slm_gui):
        super(calibration_responsivenessUi, self).__init__(slm_gui, 'calibration_responsiveness')

    def _connect(self):
        self.offset_slider.valueChanged.connect(self.update_offset_lineedit)
        self.offset_lineEdit.returnPressed.connect(self.update_offset_slider)

    def update_offset_lineedit(self):
        """Update the offset line edit from the offset slider position."""
        steps = self.offset_slider.value()
        value = 2 * steps / 100.
        self.offset_lineEdit.setText('%g' % value)

    def update_offset_slider(self):
        """Update the offset slider from the offset line edit."""
        value = float(self.offset_lineEdit.text())
        steps = 100 * value / 2.
        self.offset_slider.setValue(steps)

    def get_params(self):
        """Return the calibration grey level and the axis to apply it along.

        Returns:
            tuple: ``(grey_level, axis)`` where ``grey_level`` is in radians and ``axis`` is 0 or 1.
        """
        return np.pi * float(self.offset_lineEdit.text()), int(self.spinBox_axis.value())


class gratingsUi(BaseUi):
    """GUI for the :func:`gratings` pattern generator: a steerable linear (grating) phase ramp."""

    def __init__(self, slm_gui):
        super(gratingsUi, self).__init__(slm_gui, 'gratings')

    def _connect(self):
        self.pushButton_center.clicked.connect(lambda: self.update_gratings('center'))
        self.pushButton_up.clicked.connect(lambda: self.update_gratings('up'))
        self.pushButton_down.clicked.connect(lambda: self.update_gratings('down'))
        self.pushButton_left.clicked.connect(lambda: self.update_gratings('left'))
        self.pushButton_right.clicked.connect(lambda: self.update_gratings('right'))
        self.gratingx_lineEdit.textChanged.connect(self.slm_gui.make)
        self.gratingy_lineEdit.textChanged.connect(self.slm_gui.make)

    def update_gratings(self, direction):
        """Nudge the grating constants in a given direction by the configured step size.

        Args:
            direction (str): One of ``'center'``, ``'up'``, ``'down'``, ``'left'`` or ``'right'``.
        """
        step = float(self.lineEdit_step.text())
        grating_x = float(self.gratingx_lineEdit.text())
        grating_y = float(self.gratingy_lineEdit.text())
        if direction == 'center':
            self.gratingx_lineEdit.setText(str(0))
            self.gratingy_lineEdit.setText(str(0))
        elif direction == 'up':
            self.gratingy_lineEdit.setText('%g' % (grating_y + step))
        elif direction == 'down':
            self.gratingy_lineEdit.setText('%g' % (grating_y - step))
        elif direction == 'left':
            self.gratingx_lineEdit.setText('%g' % (grating_x + step))
        elif direction == 'right':
            self.gratingx_lineEdit.setText('%g' % (grating_x - step))

    def get_params(self):
        """Return the grating constants along x and y, defaulting empty fields to zero.

        Returns:
            tuple: ``(grating_x, grating_y)`` as floats.
        """
        grating_x = self.gratingx_lineEdit.text()
        grating_y = self.gratingy_lineEdit.text()
        if grating_x == '':
            grating_x = 0
        if grating_y == '':
            grating_y = 0
        return float(grating_x), float(grating_y)


class astigmatismUi(BaseUi):
    """GUI for the :func:`astigmatism` pattern generator, with amplitude and angle controls."""

    def __init__(self, slm_gui):
        super(astigmatismUi, self).__init__(slm_gui, 'astigmatism')

    def _connect(self):
        self.amplitude_step_lineEdit.returnPressed.connect(self.update_amplitude_lineedit)
        self.amplitude_offset_lineEdit.returnPressed.connect(self.update_amplitude_lineedit)
        self.amplitude_slider.valueChanged.connect(self.update_amplitude_lineedit)
        self.amplitude_lineEdit.returnPressed.connect(self.update_amplitude_slider)
        self.amplitude_slider.valueChanged.connect(self.slm_gui.make)

        self.angle_step_lineEdit.returnPressed.connect(self.update_angle_lineedit)
        self.angle_offset_lineEdit.returnPressed.connect(self.update_angle_lineedit)
        self.angle_slider.valueChanged.connect(self.update_angle_lineedit)
        self.angle_lineEdit.returnPressed.connect(self.update_angle_slider)
        self.angle_slider.valueChanged.connect(self.slm_gui.make)

    def update_amplitude_lineedit(self):
        """Update the amplitude line edit from the slider, step size and offset fields."""
        try:
            step_size = float(self.amplitude_step_lineEdit.text())
        except ValueError:
            amplitude = float(self.amplitude_lineEdit.text())
            if amplitude != 0:
                step_size = 0.01 * amplitude
            else:
                step_size = 0.0001
            self.amplitude_step_lineEdit.setText(str(step_size))
        try:
            offset = float(self.amplitude_offset_lineEdit.text())
        except ValueError:
            offset = float(self.amplitude_lineEdit.text())
            self.amplitude_offset_lineEdit.setText(str(offset))
        steps = self.amplitude_slider.value()
        value = offset + steps * step_size

        self.amplitude_lineEdit.setText('%g' % value)

    def update_amplitude_slider(self):
        """Update the amplitude slider position from the amplitude, step size and offset fields."""
        value = float(self.amplitude_lineEdit.text())
        step_size = float(self.amplitude_step_lineEdit.text())
        offset = float(self.amplitude_offset_lineEdit.text())

        steps = int((value - offset) / step_size)
        self.amplitude_slider.setValue(steps)

    def update_angle_lineedit(self):
        """Update the angle line edit from the slider, step size and offset fields."""
        try:
            step_size = float(self.angle_step_lineEdit.text())
        except ValueError:
            step_size = 1
            self.angle_step_lineEdit.setText(str(step_size))
        try:
            offset = float(self.angle_offset_lineEdit.text())
        except ValueError:
            offset = float(self.angle_lineEdit.text())
            self.angle_offset_lineEdit.setText(str(offset))
        steps = self.angle_slider.value()
        value = offset + steps * step_size

        self.angle_lineEdit.setText('%g' % value)

    def update_angle_slider(self):
        """Update the angle slider position from the angle, step size and offset fields."""
        value = float(self.angle_lineEdit.text())
        step_size = float(self.angle_step_lineEdit.text())
        offset = float(self.angle_offset_lineEdit.text())

        steps = int((value - offset) / step_size)
        self.angle_slider.setValue(steps)

    def get_params(self):
        """Return the astigmatism amplitude and angle.

        Returns:
            tuple: ``(amplitude, angle)`` where ``angle`` is in degrees.
        """
        amplitude = float(self.amplitude_lineEdit.text())
        angle = float(self.angle_lineEdit.text())
        return amplitude, angle


class focusUi(BaseUi):
    """GUI for the :func:`focus` pattern generator: a quadratic (lens) phase profile."""

    def __init__(self, slm_gui):
        super(focusUi, self).__init__(slm_gui, 'focus')

    def _connect(self):
        # Connects the offset slider to the lineEdits
        self.lineEdit_step.returnPressed.connect(self.update_lineedit)
        self.lineEdit_offset.returnPressed.connect(self.update_lineedit)
        self.slider.valueChanged.connect(self.update_lineedit)
        self.lineEdit_value.returnPressed.connect(self.update_slider)
        self.slider.valueChanged.connect(self.slm_gui.make)

    def update_lineedit(self):
        """Update the value line edit from the slider, step size and offset fields."""
        step_size = float(self.lineEdit_step.text())
        offset = float(self.lineEdit_offset.text())
        steps = self.slider.value()
        value = offset + steps * step_size

        self.lineEdit_value.setText('%g' % value)

    def update_slider(self):
        """Update the slider position from the value, step size and offset fields."""
        value = float(self.lineEdit_value.text())
        step_size = float(self.lineEdit_step.text())
        offset = float(self.lineEdit_offset.text())

        steps = int((value - offset) / step_size)
        self.slider.setValue(steps)

    def get_params(self):
        """Return the lens curvature.

        Returns:
            tuple: ``(curvature,)``.
        """
        curvature = float(self.lineEdit_value.text())
        return curvature,


class vortexbeamUi(BaseUi):
    """GUI for the :func:`vortexbeam` pattern generator, with order, angle and centre controls."""

    def __init__(self, slm_gui):
        super(vortexbeamUi, self).__init__(slm_gui, 'vortexbeam')

    def _connect(self):
        self.pushButton_flip.clicked.connect(self.flip)

        self.slider_angle.valueChanged.connect(
            lambda: self.lineEdit_angle.setText('%g' % self.slider_angle.value()))
        self.lineEdit_angle.textChanged.connect(
            lambda: self.slider_angle.setValue(int(float(self.lineEdit_angle.text()))))

        self.slider_center_x.valueChanged.connect(
            lambda: self.lineEdit_center_x.setText('%g' % (self.slider_center_x.value() / 100)))
        self.slider_center_y.valueChanged.connect(
            lambda: self.lineEdit_center_y.setText('%g' % (self.slider_center_y.value() / 100)))
        self.lineEdit_center_x.textChanged.connect(
            lambda: self.slider_center_x.setValue(int(100 * float(self.lineEdit_center_x.text()))))
        self.lineEdit_center_y.textChanged.connect(
            lambda: self.slider_center_y.setValue(int(100 * float(self.lineEdit_center_y.text()))))

        self.lineEdit_order.textChanged.connect(self.slm_gui.make)
        self.lineEdit_angle.textChanged.connect(self.slm_gui.make)
        self.lineEdit_center_x.textChanged.connect(self.slm_gui.make)
        self.lineEdit_center_y.textChanged.connect(self.slm_gui.make)

    def flip(self):
        """Flip the sign of the vortex order."""
        order = int(float(self.lineEdit_order.text()))
        self.lineEdit_order.setText(str(-order))

    def get_params(self):
        """Return the vortex order, angle and centre.

        Returns:
            tuple: ``(order, angle, (center_x, center_y))`` with ``angle`` in degrees.
        """
        order = int(float(self.lineEdit_order.text()))
        angle = float(self.lineEdit_angle.text())
        center_x = float(self.lineEdit_center_x.text())
        center_y = float(self.lineEdit_center_y.text())
        return order, angle, (center_x, center_y)


class multispot_gratingUi(BaseUi):
    """GUI for the :func:`multispot_grating` pattern generator that splits the SLM into segments."""

    def __init__(self, slm_gui):
        super(multispot_gratingUi, self).__init__(slm_gui, 'multispot_grating')

    def _connect(self):
        self.slider_grating.valueChanged.connect(
            lambda: self.lineEdit_grating.setText('%g' % (self.slider_grating.value() / 100)))
        self.lineEdit_grating.textChanged.connect(
            lambda: self.slider_grating.setValue(int(100 * float(self.lineEdit_grating.text()))))

        self.lineEdit_grating.textChanged.connect(self.slm_gui.make)
        self.lineEdit_spots.textChanged.connect(self.slm_gui.make)

    def get_params(self):
        """Return the grating constant and the number of spots.

        Returns:
            tuple: ``(grating_const, n_spot)``.
        """
        spots = int(float(self.lineEdit_spots.text()))
        grating = float(self.lineEdit_grating.text())
        return grating, spots


class linear_lutUi(BaseUi):
    """GUI for the :func:`linear_lut` pattern generator, with contrast and offset controls."""

    def __init__(self, slm_gui):
        super(linear_lutUi, self).__init__(slm_gui, 'linear_lut')

    def _connect(self):
        # Connects the offset slider to the lineEdits
        self.offset_lineEdit_step.returnPressed.connect(self.update_offset_lineedit)
        self.offset_lineEdit_offset.returnPressed.connect(self.update_offset_lineedit)
        self.offset_slider.valueChanged.connect(self.update_offset_lineedit)
        self.offset_lineEdit.returnPressed.connect(self.update_offset_slider)
        self.offset_slider.valueChanged.connect(self.slm_gui.make)

        # Connects the contrast slider to the lineEdits
        self.contrast_lineEdit_step.returnPressed.connect(self.update_contrast_lineedit)
        self.contrast_lineEdit_offset.returnPressed.connect(self.update_contrast_lineedit)
        self.contrast_slider.valueChanged.connect(self.update_contrast_lineedit)
        self.contrast_lineEdit.returnPressed.connect(self.update_contrast_slider)
        self.contrast_slider.valueChanged.connect(self.slm_gui.make)

    def update_offset_lineedit(self):
        """Update the offset line edit from the slider, step size and offset fields."""
        step_size = float(self.offset_lineEdit_step.text())
        offset = float(self.offset_lineEdit_offset.text())
        steps = self.offset_slider.value()
        value = offset + steps * step_size

        self.offset_lineEdit.setText('%g' % value)

    def update_offset_slider(self):
        """Update the offset slider position from the value, step size and offset fields."""
        value = float(self.offset_lineEdit.text())
        step_size = float(self.offset_lineEdit_step.text())
        offset = float(self.offset_lineEdit_offset.text())

        steps = int((value - offset) / step_size)
        self.offset_slider.setValue(steps)

    def update_contrast_lineedit(self):
        """Update the contrast line edit from the slider, step size and offset fields."""
        step_size = float(self.contrast_lineEdit_step.text())
        offset = float(self.contrast_lineEdit_offset.text())
        steps = self.contrast_slider.value()
        value = offset + steps * step_size

        self.contrast_lineEdit.setText('%g' % value)

    def update_contrast_slider(self):
        """Update the contrast slider position from the value, step size and offset fields."""
        value = float(self.contrast_lineEdit.text())
        step_size = float(self.contrast_lineEdit_step.text())
        offset = float(self.contrast_lineEdit_offset.text())

        steps = int((value - offset) / step_size)
        self.contrast_slider.setValue(steps)

    def get_params(self):
        """Return the LUT contrast and offset.

        Returns:
            tuple: ``(contrast, offset)``.
        """
        contrast = float(self.contrast_lineEdit.text())
        offset = float(self.offset_lineEdit.text())
        return contrast, offset
