# -*- coding: utf-8 -*-
"""Thorlabs FW212C 12-position motorised filter wheel (serial over VISA)."""
import os

import pyvisa as visa

from pyopenlab.instrument import Instrument
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic


class FW212C(Instrument):
    """Thorlabs FW212C filter wheel controlled over a serial VISA resource.

    The wheel uses a simple ASCII command set (e.g. ``pos=``, ``pos?``)
    terminated with carriage returns. On construction the speed, sensor mode and
    position count are configured.
    """

    def __init__(self, address='ASRLCOM7::INSTR'):
        """Open the VISA resource and apply default wheel settings.

        Args:
            address: VISA resource string for the serial port (default
                ``'ASRLCOM7::INSTR'``).
        """
        self.visa_address = str(address)
        self.baud_rate = 115200
        self.num_position = 12
        self.sept_str = "\r"
        self.prompt_str = ">"
        rm = visa.ResourceManager()
        self.device = rm.open_resource(self.visa_address,
                                       baud_rate=self.baud_rate,
                                       read_termination=self.sept_str,
                                       write_termination='',
                                       timeout=1000)
        self.setSpeedMode(1)
        self.setSensorMode(0)
        self.setPositionCount(self.num_position)

    def clear(self):
        """Consume and discard one line from the device (e.g. the command echo)."""
        self.device.read()

    def write(self, msg):
        """Send a command (carriage-return terminated) and discard the echo.

        Args:
            msg: Command string without the terminator.
        """
        self.device.write(msg + self.sept_str)
        self.clear()

    def query(self, msg):
        """Send a query and return the integer response.

        Args:
            msg: Query string without the terminator.

        Returns:
            The integer parsed from the device's reply line.
        """
        self.device.query(msg + self.sept_str)
        return int(self.device.read())

    def setPosition(self, position):
        """Move the wheel to the given 1-based filter position."""
        self.write("pos=" + str(position))

    def getPosition(self):
        """Return the current 1-based filter position."""
        pos = self.query("pos?")
        return int(pos)

    position = property(getPosition, setPosition)

    def setPositionCount(self, posCount):
        """Set the number of filter positions on the installed wheel."""
        self.write("pcount=" + str(int(posCount)))

    def getPositionCount(self):
        """Return the configured number of filter positions."""
        return int(self.query("pcount?"))

    def setSpeedMode(self, mode):
        """Set the wheel speed mode (0 = slow, 1 = fast)."""
        self.write("speed=" + str(int(mode)))

    def getSpeedMode(self):
        """Return the wheel speed mode (0 = slow, 1 = fast)."""
        return int(self.query("speed?"))

    def setSensorMode(self, mode):
        """Set the position-sensor mode (0 = off when idle, 1 = always on)."""
        self.write("sensors=" + str(int(mode)))

    def getSensorMode(self):
        """Return the position-sensor mode (0 = off when idle, 1 = always on)."""
        return int(self.query("sensors?"))

    def saveSettings(self):
        """Persist the current settings to the controller's non-volatile memory."""
        self.write("save")

    def shutdown(self):
        """Close the VISA connection."""
        self.device.close()

    def get_qt_ui(self):
        """Return a Qt control widget for this filter wheel."""
        return FW212C_UI(self)


class FW212C_UI(QtWidgets.QWidget, UiTools):
    """Qt panel with one radio button per filter-wheel position."""

    def __init__(self, fw):
        """Load the .ui file and wire each position radio button.

        Args:
            fw: The :class:`FW212C` instance to control.
        """
        super(FW212C_UI, self).__init__()
        self.fw = fw
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'thorlabs_fw212c.ui'), self)
        for button in range(1, 13):  #1-12
            eval('self.radioButton_' + str(button) + '.clicked.connect(self.button_pressed)')

    def button_pressed(self):
        '''buttons are called radioButton_x'''
        self.fw.position = int(self.sender().objectName().split('_')[-1])


if __name__ == '__main__':
    fw = FW212C()
    fw.show_gui(blocking=False)
