# -*- coding: utf-8 -*-
"""Spatial light modulator (SLM) instrument, phase display widget and control GUI.

Provides the :class:`Slm` instrument, which builds greyscale phase holograms by sequentially
applying named pattern generators, the :class:`SlmDisplay` widget that renders those holograms on
the SLM panel, and the :class:`SlmUi` control GUI.
"""

import math
import os

import numpy as np
import pyqtgraph.dockarea as dockarea
from scipy.interpolate import interp1d

from pyopenlab.instrument import Instrument
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import get_qt_app
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic

from . import gui
from . import pattern_generators


def zernike_polynomial(array_size, n, m, beam_size=1, unit_circle=True):
    """Create an image of the Zernike polynomial of order (n, m).

    See https://en.wikipedia.org/wiki/Zernike_polynomials. The polynomials are only defined inside
    the unit circle, but the output of this function is a square array, so the corners are wrong.

    Args:
        array_size (int or tuple): Side length in pixels. An int gives a square array; a 2-tuple
            gives (height, width).
        n (int): Radial order of the polynomial. Must satisfy ``n >= 0`` and ``n >= abs(m)``.
        m (int): Azimuthal order. A negative value selects the odd (sine) variant.
        beam_size (float): Radius (in normalised units) the polynomial is scaled to.
        unit_circle (bool): If True, zero the polynomial outside the unit circle.

    Returns:
        numpy.ndarray: The Zernike polynomial, normalised to unit power within the unit circle.

    Raises:
        AssertionError: If ``n < 0`` or ``abs(m) > n``.
    """
    assert n >= 0
    if m < 0:
        odd = True
        m = np.abs(m)
    else:
        odd = False
    assert n >= m

    if type(array_size) == int:
        array_size = (array_size, array_size)
    im_rat = array_size[1] / array_size[0]
    if im_rat >= 1:
        _x = np.linspace(-im_rat, im_rat, array_size[1])
        _y = np.linspace(-1, 1, array_size[0])
    else:
        _x = np.linspace(-1, 1, array_size[1])
        _y = np.linspace(-1 / im_rat, 1 / im_rat, array_size[0])
    x, y = np.meshgrid(_x, _y)
    # By normalising the radius to the beamsize, we can make Zernike polynomials of different sizes
    rho = np.sqrt(x**2 + y**2) / beam_size
    phi = np.arctan2(x, y)

    summ = []
    for k in range(1 + (n - m) // 2):
        summ += [((-1)**k * math.factorial(n - k) * (rho**(n - 2 * k))) /
                 (math.factorial(k) * math.factorial((n + m) // 2 - k) *
                  math.factorial((n - m) // 2 - k))]
    r = np.sum(summ, 0)
    if (n - m) % 2:
        r = 0

    # Limiting the polynomial to the unit circle, where it is defined:
    if unit_circle:
        r[rho > 1] = 0

    if odd:
        zernike = r * np.sin(m * phi)
    else:
        zernike = r * np.cos(m * phi)

    normalised = zernike / np.sqrt(np.sum(zernike[rho < 1] * zernike[rho < 1]))
    return normalised


class SlmDisplay(QtWidgets.QWidget):
    """Widget for displaying greyscale holograms on the SLM panel.

    It is a plain window using a QImage + QLabel.setPixmap combination to display phase arrays.
    """
    update_image = QtCore.Signal(np.ndarray)

    def __init__(self,
                 shape=(1000, 1000),
                 resolution=(1, 1),
                 bitness=8,
                 hide_border=True,
                 lut=None):
        """Build the SLM display widget.

        Args:
            shape (tuple): Width and height of the SLM panel in pixels.
            resolution (tuple): Per-axis downscaling factors applied to ``shape``.
            bitness (int): Number of addressing (greyscale) levels of the SLM.
            hide_border (bool): Whether to hide the standard OS window border. Set False only for
                debugging.
            lut (tuple or str or None): Parameters passed to :meth:`set_lut`. The default LUT maps
                phase from 0 to 2 pi onto greyscale values 0 to ``2**bitness``.
        """
        super(SlmDisplay, self).__init__()

        self._pixels = [int(x[0] / x[1]) for x in zip(shape, resolution)]
        self._bitness = bitness

        self._QImage = None
        self._QLabel = None
        self._make_gui(hide_border)

        self.LUT = None
        if lut is None:
            lut = (2**self._bitness, 0)
        self.set_lut(lut)

        self.update_image.connect(self._set_image, type=QtCore.Qt.QueuedConnection)

    def _make_gui(self, hide_border=True):
        """Create and apply the widget layout.

        Args:
            hide_border (bool): See :meth:`__init__`.
        """
        self._QLabel = QtWidgets.QLabel(self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._QLabel)
        self.setLayout(layout)

        self.setWindowTitle('SLM Phase')
        if hide_border:
            self.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.FramelessWindowHint |
                                QtCore.Qt.WindowStaysOnTopHint)

    def set_lut(self, lut):
        """Set the lookup table that maps phase (in radians) to greyscale display values.

        Args:
            lut (str or array-like): A filename to load with :func:`numpy.loadtxt`, a 1D array of
                :class:`numpy.poly1d` coefficients, or a 2D array of ``[phase, gray_level]`` pairs
                to interpolate between.
        """
        if type(lut) == str:
            lut = np.loadtxt(lut)

        lut = np.array(lut)
        if len(lut.shape) == 1:
            # Assumes the lut corresponds to poly1d parameters
            params = [x / (2 * np.pi) for x in lut]
            self.LUT = np.poly1d(params)
        elif len(lut.shape) == 2:
            phase = lut[0]
            gray_level = lut[1]
            self.LUT = interp1d(phase, gray_level)

    def set_image(self, phase, slm_monitor=None):
        """Convert a phase array to greyscale, emit it for display, and optionally reposition.

        Args:
            phase (numpy.ndarray): Phase array in radians.
            slm_monitor (int, optional): If given, move the widget onto this monitor index.

        Returns:
            numpy.ndarray: The phase mapped through the LUT to SLM display values.
        """
        # Makes phase go from 0 to 2*pi, and removes floating point errors
        phase = (phase + 0.1 * np.pi / 2**self._bitness) % (2 *
                                                            np.pi) - 0.1 * np.pi / 2**self._bitness
        # Makes phase go from -pi to pi
        phase -= np.pi
        # Transform into SLM display values
        phase = self.LUT(phase)

        self.update_image.emit(phase)

        if slm_monitor is not None:
            app = get_qt_app()
            desktop = app.desktop()
            slm_screen = desktop.screen(slm_monitor)
            assert isinstance(slm_monitor, int)
            assert desktop.screenCount() > slm_monitor >= 0
            self.move(slm_screen.x(), slm_screen.y())
        return phase

    def _set_image(self, phase):
        """Render a greyscale array onto the QLabel pixmap.

        Args:
            phase (numpy.ndarray): Array of display values to render.

        Raises:
            ValueError: If ``self._bitness`` is not 8 (other bit depths are not implemented).
        """
        img = phase.ravel()

        if self._bitness == 8:
            self._QImage = QtGui.QImage(img.astype(np.uint8), phase.shape[1], phase.shape[0],
                                        QtGui.QImage.Format_Grayscale8)
        else:
            raise ValueError('Bitness %g is not implemented' % self._bitness)

        self._QLabel.setPixmap(QtGui.QPixmap(self._QImage))


class Slm(Instrument):
    """Spatial light modulator instrument that builds phase holograms from pattern generators."""

    def __init__(self, options, slm_monitor, correction_phase=None, display_kwargs=None, **kwargs):
        """Build the SLM instrument.

        Args:
            options (list of str): Names of the functionalities the SLM should have (e.g.
                ``gratings``, ``vortexbeam``, ``focus``, ``astigmatism``, ``linear_lut``). The order
                matters: the generators act on the phase pattern sequentially (see
                :meth:`make_phase`).
            slm_monitor (int): Monitor index for the SLM. See :meth:`_get_monitor_size`.
            correction_phase (numpy.ndarray or str, optional): Spatial correction some SLMs require
                for a flat phase. May be an array or a filename to load.
            display_kwargs (dict, optional): Keyword arguments forwarded to :class:`SlmDisplay`.
            **kwargs: Unused; accepted for compatibility.

        Raises:
            AssertionError: If ``correction_phase`` is an array whose shape does not match the
                detected panel shape.
        """
        super(Slm, self).__init__()

        self._shape = self._get_monitor_size(slm_monitor)
        if correction_phase is None:
            self._correction = np.zeros(self._shape[::-1])
        elif type(correction_phase) == str:
            self._correction = np.loadtxt(correction_phase)
        else:
            assert correction_phase.shape == self._shape
            self._correction = correction_phase

        self.phase = None
        self.Display = None
        if display_kwargs is None:
            self.display_kwargs = dict()
        else:
            self.display_kwargs = display_kwargs
        self.options = options

    @staticmethod
    def _get_monitor_size(monitor_index):
        """Detect the SLM panel size from the monitor geometry.

        Args:
            monitor_index (int): Monitor number.

        Returns:
            list: Width and height of the monitor in pixels.

        Raises:
            AssertionError: If ``monitor_index`` is out of range.
        """
        app = get_qt_app()
        desktop = app.desktop()
        assert 0 <= monitor_index < desktop.screenCount(
        ), 'monitor_index must be between 0 and the number of monitors'
        slm_screen = desktop.screen(monitor_index)

        return [slm_screen.width(), slm_screen.height()]

    def make_phase(self, parameters):
        """Create and return the phase pattern.

        Iterates over ``self.options``, looking up each pattern generator by name and applying them
        sequentially to an array initially full of zeros.

        Args:
            parameters (dict): Keys correspond to ``self.options`` entries; each value is the
                sequence of positional arguments passed to the matching pattern generator.

        Returns:
            numpy.ndarray: The combined phase pattern.
        """
        self._logger.debug('Making phases: %s, %s' % (self._shape, parameters))
        self.phase = np.zeros(self._shape[::-1])
        for option in self.options:
            self._logger.debug('Making phase: %s' % option)
            try:
                self.phase = getattr(pattern_generators, option)(self.phase, *parameters[option])
            except Exception as e:
                self._logger.warn('Failed because: %s' % e)
        self._logger.debug('Finished making phases')
        return self.phase

    def display_phase(self, phase, slm_monitor=None):
        """Display a phase array, creating the display widget if necessary.

        Args:
            phase (numpy.ndarray): 2D array of phase values.
            slm_monitor (int, optional): Index of the monitor to display the array on.

        Returns:
            numpy.ndarray: The phase (including correction) mapped through the LUT.
        """
        if self.Display is None:
            self.Display = SlmDisplay(self._shape, **self.display_kwargs)

        self._logger.debug("Setting phase (min, max)=(%g, %g); shape=%s; monitor=%s" %
                           (np.min(phase), np.max(phase), np.shape(phase), slm_monitor))
        phase = self.Display.set_image(phase + self._correction, slm_monitor=slm_monitor)

        if self.Display.isHidden():
            self.Display.show()
        return phase

    def get_qt_ui(self):
        """Return a new Qt control GUI for this SLM.

        Returns:
            SlmUi: The control widget bound to this instrument.
        """
        return SlmUi(self)


class SlmUi(QtWidgets.QWidget, UiTools):
    """Qt control GUI for an :class:`Slm`, assembling one dock per SLM option."""

    def __init__(self, slm):
        """Build the control GUI.

        Args:
            slm (Slm): The SLM instrument to control.
        """
        super(SlmUi, self).__init__()
        self.all_widgets = None
        self.all_docks = None
        self.PhaseDisplay = None
        self.dockarea = None
        self.SLM = slm
        self.setup_gui()

    def setup_gui(self):
        """Create a DockArea and fill it with one widget per SLM option.

        For each option, the matching UI is looked up from :mod:`gui` by name, loaded into a widget
        and added to the DockArea.
        """
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'ui_base.ui'), self)
        self.dockarea = dockarea.DockArea()
        self.splitter.insertWidget(0, self.dockarea)
        self.dockarea.show()  # Absolutely no idea why this is needed

        self.all_widgets = dict()
        self.all_docks = []
        for option in self.SLM.options:
            widget = getattr(gui, '%sUi' % option)(self)
            dock = dockarea.Dock(option)
            dock.addWidget(widget)
            self.dockarea.addDock(dock, 'bottom')
            self.all_widgets[option] = widget
            self.all_docks += [dock]
        self.make_pushButton.pressed.connect(self.make)
        self.save_pushButton.pressed.connect(self.save)
        self.load_pushButton.pressed.connect(self.load)

    @property
    def settings_filename(self):
        """str: Path of the settings file, defaulting to ``settings.ini`` beside this module."""
        filename = self.filename_lineEdit.text()
        if filename == '':
            filename = os.path.join(os.path.dirname(__file__), 'settings.ini')
            self.filename_lineEdit.setText(filename)
        return filename

    @settings_filename.setter
    def settings_filename(self, value):
        self.filename_lineEdit.setText(value)

    def make(self):
        """Build the phase from the current GUI parameters and display it on the SLM and preview."""
        parameters = self.get_gui_phase_params()
        self.SLM._logger.debug('SlmUi.make called with args=%s' % (parameters,))
        phase = self.SLM.make_phase(parameters)

        slm_monitor = self.slm_monitor_lineEdit.text()
        if slm_monitor == '':
            slm_monitor = None
        else:
            slm_monitor = int(slm_monitor)

        phase = self.SLM.display_phase(np.copy(phase), slm_monitor=slm_monitor)

        # The data is transposed according to the pyqtgraph documentation for axis ordering
        # http://www.pyqtgraph.org/documentation/widgets/imageview.html
        self.PhaseDisplay.setImage(np.copy(phase).transpose())

    def save(self):
        """Save the base GUI settings and every option widget's settings to the settings file."""
        gui_settings = QtCore.QSettings(self.settings_filename, QtCore.QSettings.IniFormat)
        self.save_settings(gui_settings, 'base')
        for name, widget in list(self.all_widgets.items()):
            widget.save_settings(gui_settings, name)
        return

    def load(self):
        """Load the base GUI settings and every option widget's settings from the settings file."""
        gui_settings = QtCore.QSettings(self.settings_filename, QtCore.QSettings.IniFormat)
        self.load_settings(gui_settings, 'base')
        for name, widget in list(self.all_widgets.items()):
            widget.load_settings(gui_settings, name)
        return

    def get_gui_phase_params(self):
        """Collect phase parameters from every option widget.

        Returns:
            dict: Keys are the option names; values are whatever each widget returns from
            ``get_params``.
        """
        all_params = dict()
        for name, widget in list(self.all_widgets.items()):
            all_params[name] = widget.get_params()
        self.SLM._logger.debug('get_gui_phase_params: %s' % all_params)
        return all_params

    def closeEvent(self, event):
        """Close the SLM display widget when the control GUI is closed.

        Args:
            event (QtGui.QCloseEvent): The Qt close event.
        """
        if self.SLM.Display is not None:
            self.SLM.Display.close()


if __name__ == "__main__":
    settings = [
        'gratings', 'vortexbeam', 'focus', 'astigmatism', 'linear_lut', 'constant',
        'calibration_responsiveness']
    SLM = Slm(settings, 1)
    SLM._logger.setLevel('DEBUG')
    SLM.show_gui()
