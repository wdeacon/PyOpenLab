# -*- coding: utf-8 -*-
"""PyOpenLab driver and UI for the NKT Varia tunable filter (SuperK EVO system).

Provides simple set-wavelength and get-wavelength/bandwidth control. An optional
shutter can be supplied; if set, it is closed while the wavelength or bandwidth is
changed and reopened afterwards (only if it was open), to protect downstream optics
during filter movement.

Relies on the ``nkt_tools`` library (``pip install nkt_tools``).

Note:
    Could be extended to also control the SuperK EVO white-light laser. There is
    currently no shared monochromator parent class; this driver inherits from both
    :class:`~pyopenlab.instrument.Instrument` and ``nkt_tools.varia.Varia``.
"""

import os
import time

import nkt_tools.NKTP_DLL as nkt
import nkt_tools.varia
import numpy as np
import tqdm

import pyopenlab
from pyopenlab.instrument import Instrument
from pyopenlab.instrument.shutter.thorlabs_sc10 import ThorLabsSC10
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic
from pyopenlab.utils.notified_property import NotifiedProperty

# shutter = ThorLabsSC10('COM11')


class Varia(Instrument, nkt_tools.varia.Varia):
    """NKT Varia tunable bandpass filter.

    Wavelength is expressed as the centre of the band defined by the short and long
    setpoints; bandwidth is their difference. If a shutter is provided it is closed
    during moves for safety.

    Attributes:
        shutter: A :class:`~pyopenlab.instrument.shutter.Shutter` instance, or
            ``None`` if no shutter is managed.
    """

    def __init__(self, shutter=None):
        """Initialise the Varia and move to a default 600 nm / 10 nm band.

        Args:
            shutter: Optional shutter to close during wavelength/bandwidth changes.
                Must be a :class:`~pyopenlab.instrument.shutter.Shutter` subclass;
                anything else is ignored (and a warning is printed).
        """
        Instrument.__init__(self)
        nkt_tools.varia.Varia.__init__(self)

        if issubclass(type(shutter), pyopenlab.instrument.shutter.Shutter):
            self.shutter = shutter
        else:
            self.shutter = None
            print(
                '\nWarning: No Shutter set for Varia! set_wavelength() and set_bandwidth() operations will not close shutter before setting new wavelength'
            )

        self.set_wavelength(600, 10)

    def get_bandwidth(self):
        """Return the current bandwidth (FWHM) in nm.

        Returns:
            float: Difference between the long and short setpoints, in nm.
        """
        bandwidth = self.long_setpoint - self.short_setpoint
        return bandwidth

    def get_wavelength(self):
        """Return the current centre wavelength in nm.

        Returns:
            float: Midpoint of the short and long setpoints, in nm.
        """
        wavelength = (self.long_setpoint + self.short_setpoint) / 2
        return wavelength

    def is_filter_moving(self):
        """Check whether any of the three filter wheels is currently moving.

        Reads the Varia status register (0x66) over the NKT bus and inspects the
        moving bits.

        Returns:
            bool: ``True`` if a filter is moving, otherwise ``False``.

        Note:
            The final ``else`` branch uses ``filter_moving == False`` (a comparison,
            not an assignment), so when bits 12-14 are all zero ``filter_moving`` is
            never assigned and a ``NameError`` is raised. The bit indexing also reads
            characters of ``bin(byte)`` (which includes the ``0b`` prefix). Both are
            latent bugs; left unchanged to avoid altering behaviour.
        """
        register_address = 0x66
        result, byte = nkt.registerReadU16(self.portname, self.module_address, register_address, -1)
        bits = bin(byte)

        if len(bits) <= 11:
            filter_moving = False
        elif bits[12] + bits[13] + bits[14] != 0:
            filter_moving = True
        else:
            filter_moving == False

        return filter_moving

    def set_wavelength(self, wavelength, bandwidth=10):
        """Set the centre wavelength (and bandwidth), waiting for the move to finish.

        If a shutter is configured and currently open it is closed before the move
        and reopened afterwards. Prints a warning if the requested band falls outside
        the reliable 400-840 nm range.

        Args:
            wavelength (float): Target centre wavelength in nm.
            bandwidth (float): Bandwidth (FWHM) in nm. Defaults to 10.
        """
        ## Close shutter if set and if open
        if self.shutter is not None:
            shutter_state = self.shutter.get_state()

            if shutter_state == 'Open':
                self.shutter.close_shutter()

        ## Change wavelength
        self.short_setpoint = wavelength - (bandwidth / 2)
        self.long_setpoint = wavelength + (bandwidth / 2)
        while self.is_filter_moving() == True:
            time.sleep(0.1)

        ## Open shutter if it was open
        if self.shutter is not None and shutter_state == 'Open':
            self.shutter.open_shutter()

        ## Warning if wavelength is out of recommended range
        if self.long_setpoint > 850 or self.short_setpoint < 390:
            print('Warning: Varia wavelength is outside of reliable range (400 - 840 nm)')

    def set_bandwidth(self, bandwidth):
        """Set the bandwidth while keeping the current centre wavelength.

        If a shutter is configured and currently open it is closed before the move
        and reopened afterwards. Prints warnings if the bandwidth falls outside the
        reliable 10-100 nm range or the resulting band leaves the 400-840 nm range.

        Args:
            bandwidth (float): Target bandwidth (FWHM) in nm.
        """
        ## Close shutter if set and if open
        if self.shutter is not None:
            shutter_state = self.shutter.get_state()

            if shutter_state == 'Open':
                self.shutter.close_shutter()

        ## Change bandwidth
        wavelength = self.get_wavelength()
        self.short_setpoint = wavelength - (bandwidth / 2)
        self.long_setpoint = wavelength + (bandwidth / 2)
        while self.is_filter_moving() == True:
            time.sleep(0.1)

        ## Open shutter if it was open
        if self.shutter is not None and shutter_state == 'Open':
            self.shutter.open_shutter()

        ## Warning if bandwidth is out of recommended range
        if self.get_bandwidth() < 10 or self.get_bandwidth() > 100:
            print('Warning: Varia bandwidth exceeds reliable range (10 - 100 nm FWHM)')

        ## Warning if wavelength is out of recommended range
        if self.long_setpoint > 850 or self.short_setpoint < 390:
            print('Warning: Varia wavelength is outside of reliable range (400 - 840 nm)')

    def get_qt_ui(self):
        """Return a Qt control widget for this Varia.

        Returns:
            VariaControlUI: A control panel bound to this instrument.
        """
        return VariaControlUI(self)


class VariaControlUI(QtWidgets.QWidget, UiTools):
    """Qt widget for controlling a :class:`Varia` (centre wavelength and bandwidth)."""

    def __init__(self,
                 varia,
                 ui_file=os.path.join(os.path.dirname(__file__), 'varia.ui'),
                 parent=None):
        """Build the control panel and wire it to the instrument.

        Args:
            varia (Varia): The instrument to control.
            ui_file (str): Path to the Qt Designer ``.ui`` file. Defaults to
                ``varia.ui`` next to this module.
            parent: Optional parent Qt widget.
        """
        assert isinstance(varia, Varia), "instrument must be a Varia"
        super(VariaControlUI, self).__init__()
        uic.loadUi(ui_file, self)
        self.varia = varia
        self.centre_wl_lineEdit.returnPressed.connect(self.set_wl_gui)
        self.bw_lineEdit.returnPressed.connect(self.set_bw_gui)
        self.centre_wl_lineEdit.setText(str(self.varia.get_wavelength()))
        self.bw_lineEdit.setText(str(self.varia.get_bandwidth()))

    def set_wl_gui(self):
        """Apply the centre wavelength entered in the line edit to the instrument."""
        self.varia.set_wavelength(float(self.centre_wl_lineEdit.text().strip()))

    def set_bw_gui(self):
        """Apply the bandwidth entered in the line edit to the instrument."""
        self.varia.set_bandwidth(float(self.bw_lineEdit.text().strip()))


if __name__ == "__main__":

    v = Varia(shutter=None)
    ui = VariaControlUI(varia=v)
    ui.show()
