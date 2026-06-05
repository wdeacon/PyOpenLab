# -*- coding: utf-8 -*-
"""Generic :class:`PowerMeter` base class and its live-readout Qt UI."""

import os
import threading
import time

import numpy as np

from pyopenlab.instrument import Instrument
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic
from pyopenlab.utils.notified_property import DumbNotifiedProperty
from pyopenlab.utils.notified_property import register_for_property_changes

#import winsound


class PowerMeter(Instrument):
    """Base class giving a power meter PyOpenLab functionality and a live GUI.

    The minimum needed to subclass this is to override :meth:`read_power`.

    Attributes:
        live (bool): Whether the GUI is continuously polling the meter.
        beep (bool): Whether the GUI emits an audible tone scaled to power.
    """
    live = DumbNotifiedProperty(False)
    beep = DumbNotifiedProperty(False)

    def __init__(self):
        Instrument.__init__(self)

    def read_power(self):
        """Read the current power. Must be overridden by subclasses.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError

    @property
    def power(self):
        """float: The current power, read via :meth:`read_power`."""
        return self.read_power()

    def get_qt_ui(self):
        """Return the Qt control widget for this power meter.

        Returns:
            PowerMeterUI: A widget bound to this instrument.
        """
        return PowerMeterUI(self)


class PowerMeterUI(QtWidgets.QWidget, UiTools):
    """Qt control panel with a live LCD readout for a :class:`PowerMeter`."""
    update_data_signal = QtCore.Signal(np.ndarray)

    def __init__(self, pm):
        """Build the UI and wire it to the power meter.

        Args:
            pm: The :class:`PowerMeter` instance to display and control.
        """
        super(PowerMeterUI, self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'power_meter.ui'), self)
        self.pm = pm
        self.update_condition = threading.Condition()
        self.display_thread = DisplayThread(self)
        self.SetupSignals()
        register_for_property_changes(self.pm, 'live', self.live_changed)
        register_for_property_changes(self.pm, 'beep', self.beep_changed)

    def SetupSignals(self):
        """Connect the buttons and the display thread to their handlers."""
        self.read_pushButton.clicked.connect(self.button_pressed)
        self.live_button.clicked.connect(self.button_pressed)
        self.beep_button.clicked.connect(self.beep_pressed)
        self.display_thread.ready.connect(self.update_display)

    def button_pressed(self):
        """Handle the read/live buttons and (re)start the display thread."""
        s = self.sender()
        if s == self.read_pushButton:
            self.display_thread.single_shot = True
        elif s == self.live_button:
            self.pm.live = self.live_button.isChecked()
        self.display_thread.start()

    def beep_pressed(self):
        """Toggle the meter's beep mode from the beep button."""
        self.pm.beep = self.beep_button.isChecked()

    def update_display(self, power):
        """Show a new power value on the LCD.

        Args:
            power: The power reading to display.
        """
        self.power_lcdNumber.display(float(power))

    def live_changed(self, new):
        """Sync the live button when the meter's ``live`` property changes.

        Args:
            new: The new value of ``pm.live``.
        """
        if self.live_button.isChecked() is not self.pm.live:
            self.live_button.setChecked(new)
        self.display_thread.start()

    def beep_changed(self, new):
        """Sync the beep button when the meter's ``beep`` property changes.

        Args:
            new: The new value of ``pm.beep``.
        """
        if self.beep_button.isChecked() is not self.pm.beep:
            self.beep_button.setChecked(new)


class DisplayThread(QtCore.QThread):
    """Background thread that polls the meter and emits power readings."""
    ready = QtCore.Signal(float)

    def __init__(self, parent):
        """Store the parent UI and set the default refresh rate.

        Args:
            parent: The :class:`PowerMeterUI` that owns this thread.
        """
        super(DisplayThread, self).__init__()
        self.parent = parent
        self.single_shot = False
        self.refresh_rate = 4.

    def run(self):
        """Poll the meter while live (or once for a single shot), emitting power."""
        t0 = time.time()
        beep_power = self.parent.pm.power
        while self.parent.pm.live or self.single_shot:
            p = self.parent.pm.power
            if time.time() - t0 < 1. / self.refresh_rate:
                continue
            else:
                t0 = time.time()

            if self.parent.pm.beep:
                beep_freq = 1500 * (p / beep_power)
                if 37 < beep_freq < 32767:
                    #winsound.Beep(int(beep_freq), 100)
                    pass

            self.ready.emit(p)
            if self.single_shot:
                self.single_shot = False
                break
        self.finished.emit()


class dummyPowerMeter(PowerMeter):
    """A simulated power meter returning random values, for testing."""

    def __init__(self):
        super(PowerMeter, self).__init__()

    def read_power(self):
        """Return a random power value in the range 0-10.

        Returns:
            float: A simulated power reading.
        """
        return np.random.rand() * 10


if __name__ == '__main__':
    dpm = dummyPowerMeter()
    dpm.show_gui(blocking=False)
