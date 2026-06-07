# -*- coding: utf-8 -*-
"""Driver and Qt UI for the Oxford Instruments ITC temperature controller."""

import os

from pyopenlab.instrument.temperatureControl import TemperatureControlMixin
from pyopenlab.instrument.visa_instrument import VisaInstrument
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic


class OxfordITC(VisaInstrument, TemperatureControlMixin):
    """Oxford Instruments ITC temperature controller (GPIB or serial)."""

    def __init__(self, address, **kwargs):
        """Open a connection and initialise the controller.

        The transport settings differ between GPIB and serial connections; the
        address string is inspected for ``'GPIB'`` to choose between them. On
        connection the controller is placed in remote/unlocked mode, the I/O
        buffers are cleared, and the current and target temperatures are read.

        Args:
            address (str): VISA resource address. If it contains ``'GPIB'`` a GPIB
                connection is configured, otherwise a 9600-baud serial connection.
            **kwargs: Accepted for signature compatibility; not used.
        """
        TemperatureControlMixin.__init__(self)
        if 'GPIB' in address:
            VisaInstrument.__init__(self,
                                    address,
                                    settings=dict(timeout=10000,
                                                  read_termination='\r',
                                                  write_termination='\r'))
        else:
            VisaInstrument.__init__(self,
                                    address,
                                    settings=dict(baud_rate=9600,
                                                  read_termination='\r',
                                                  write_termination='\r',
                                                  timeout=1000))

        self.setControlMode(3)

        self.params = {'T': 0, 'SetT': 0, 'PID': [0, 0, 0]}
        self.flush_input_buffer()
        self.clear_read_buffer()
        self.get_temperature()
        self.get_target_temperature()

    def __del__(self):
        """Turn off the heater, return to local mode, and close the connection."""
        try:
            self.heaterOff()
            self.setControlMode(0)
            self.instr.close()
        except:
            self._logger.warn("Couldn't close %s on port %s" % (self.__name__, self._address))

    def get_temperature(self):
        """Return the current sample temperature in Kelvin.

        Queries ``R1`` and caches the value in ``self.params['T']``.

        Returns:
            float: The current temperature in Kelvin.
        """
        temp = self.query('R1', delay=1)
        temp = float(temp[1:len(temp)])  # Remove the first character ('R')

        self.params['T'] = temp

        return temp

    def setControlMode(self, mode):
        """Set the operation mode (local or remote).

        Args:
            mode (int): One of:
                0 - LOCAL & LOCKED (default state);
                1 - REMOTE & LOCKED (front panel disabled);
                2 - LOCAL & UNLOCKED;
                3 - REMOTE & UNLOCKED (front panel active).

        Raises:
            Exception: If ``mode`` is not in ``[0, 1, 2, 3]``.
        """
        if (mode not in [0, 1, 2, 3]):
            raise Exception('valid modes are 0-3, see documentation')
        self.write('C' + str(mode))

    def get_target_temperature(self):
        """Return the target (set-point) temperature in Kelvin.

        Queries ``R0`` and caches the value in ``self.params['SetT']``.

        Returns:
            float: The target temperature in Kelvin.
        """
        temp = self.query('R0')
        temp = float(temp[1:len(temp)])  # Remove the first character ('R')

        self.params['SetT'] = temp

        return temp

    def set_target_temperature(self, temp):
        """Set the target (set-point) temperature.

        Args:
            temp (int): Target temperature in Kelvin. Cast to ``int`` before being
                sent to the instrument.
        """
        self.params['SetT'] = temp

        self.write('T' + str(int(temp)))

    def setHeaterMode(self, mode):
        """Set the heater and gas-flow mode (auto or manual).

        Args:
            mode (int): One of:
                0 - HEATER MANUAL, GAS MANUAL;
                1 - HEATER AUTO, GAS MANUAL;
                2 - HEATER MANUAL, GAS AUTO;
                3 - HEATER AUTO, GAS AUTO.

        Raises:
            Exception: If ``mode`` is not in ``[0, 1, 2, 3]``.
        """
        if (mode not in [0, 1, 2, 3]):
            raise Exception('valid modes are 0-3, see documentation')
        self.write('A' + str(mode))

        self.params['Heater'] = mode

    def setHeaterPower(self, power):
        """Set the manual heater output power.

        Args:
            power: Heater power level; cast to ``int`` before being sent.
        """
        self.params['HeaterPower'] = power
        self.write('O' + str(int(power)))

    def heaterOff(self):
        """Switch the heater to manual mode and set its power to zero."""
        self.setHeaterMode(0)
        self.setHeaterPower(0)

    def setAutoPID(self, mode):
        """Enable or disable automatic PID control.

        Args:
            mode (int): ``0`` to disable auto-PID, ``1`` to enable it.

        Raises:
            Exception: If ``mode`` is not ``0`` or ``1``.
        """
        if (mode not in [0, 1]):
            raise Exception('valid modes are 0 (off) or 1 (on)')
        self.write('L' + str(mode))

        self.params['autoPID'] = mode

    def setPID(self, P, I, D):
        """Set the manual PID control parameters.

        Args:
            P: Proportional band in Kelvin (resolution 0.001 K, ideally 5 to 50 K).
            I: Integral action time in minutes (0 to 140, ideally 1 to 10).
            D: Derivative action time in minutes (0 to 273, can be left at 0).
        """
        self.write('P' + str(P))
        self.write('I' + str(I))
        self.write('D' + str(D))

        self.params['PID'] = [P, I, D]

    def get_qt_ui(self):
        """Return a Qt widget for controlling this instrument.

        Returns:
            OxfordITCUI: A widget bound to this controller.
        """
        return OxfordITCUI(self)


class OxfordITCUI(QtWidgets.QWidget):
    """Qt control panel for an :class:`OxfordITC` instrument."""

    updateGUI = QtCore.Signal()

    def __init__(self, itc):
        """Build the UI from ``OxfordITC.ui`` and bind it to an instrument.

        Args:
            itc (OxfordITC): The instrument this panel controls.

        Raises:
            AssertionError: If ``itc`` is not an :class:`OxfordITC` instance.
        """
        assert isinstance(itc, OxfordITC), "instrument must be an Oxford ITC"
        super(OxfordITCUI, self).__init__()

        self.ITC = itc

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'OxfordITC.ui'), self)

        self.lineEditSetT.returnPressed.connect(self.setT)

        self.updateGUI.connect(self.SentUpdateGUI)
        self.SentUpdateGUI()

    def SentUpdateGUI(self):
        """Refresh the displayed temperature, set-point, and PID values."""
        self.textEditT.setText(str(self.ITC.params['T']))
        self.lineEditSetT.setText(str(self.ITC.params['SetT']))
        self.lineEditP.setText(str(self.ITC.params['PID'][0]))
        self.lineEditI.setText(str(self.ITC.params['PID'][1]))
        self.lineEditD.setText(str(self.ITC.params['PID'][2]))
        return

    def setT(self):
        """Send the set-point entered in the UI to the instrument."""
        temp = float(self.lineEditSetT.text())
        self.ITC.set_target_temperature(temp)


if __name__ == '__main__':
    ITC = OxfordITC('GPIB0::24::INSTR')

    ITC.show_gui()
