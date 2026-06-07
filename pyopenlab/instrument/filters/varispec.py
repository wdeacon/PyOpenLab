# -*- coding: utf-8 -*-
"""Driver and Qt UI for a CRi VariSpec liquid-crystal tunable filter over serial."""

import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty


class VariSpec(SerialInstrument):
    """Serial driver for a CRi VariSpec liquid-crystal tunable filter.

    The active wavelength is exposed as the :attr:`wavelength` notified property (aliased
    as :attr:`wl`); the supported range is queried as :attr:`wavelength_range`.

    Attributes:
        termination_character (str): Line terminator for serial commands.
        port_settings (dict): Pyserial port configuration for the filter.
        ignore_echo (bool): Whether the base class should discard the device's command echo.
    """

    termination_character = "\r"
    port_settings = dict(
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  #wait at most one second for a response
        writeTimeout=1,  #similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=False)
    ignore_echo = True

    def __init__(self, port):
        """Open the serial port and log the filter's supported wavelength range.

        Args:
            port (str): Serial port name (e.g. ``'COM13'``).
        """
        super().__init__(port=port)
        self._set = False
        self._logger.info(f'wavelength range = {self.wavelength_range}')

    def reset_error(self):
        """Clear the filter's error state by sending the ``R 1`` command."""
        self.write("R 1")

    def get_wavelength(self):
        """Return the current wavelength, or warn if none has been set yet.

        Returns:
            float | None: The active wavelength in nm, or None (after logging a warning)
            if :meth:`set_wavelength` has not been called this session.
        """
        if self._set:
            return float(self.query("W ?")[3:])
        else:
            self._logger.warning('wavelength has not been set')

    def set_wavelength(self, wl):
        """Command the filter to a wavelength and check the resulting error code.

        Args:
            wl (float): Target wavelength in nm; formatted to two decimal places.
        """
        self._set = True
        self.write(f'W {wl:.2f}')
        e = self.get_error()
        if e == '0':
            return
        if e == '12':
            self._logger.warning(f'{wl=} out of range')
        else:
            self._logger.warning(f'error code {e} raised')

    wavelength = NotifiedProperty(get_wavelength, set_wavelength)
    wl = wavelength

    def get_error(self):
        """Query and clear the current error code.

        Returns:
            str: The error code string reported by the ``R ?`` query (cleared afterwards).
        """
        e = self.query('R ?')[1:].strip()
        self.reset_error()
        return e

    def get_wavelength_range(self):
        """Query the filter's supported wavelength range.

        Returns:
            tuple[float, float]: The (minimum, maximum) tunable wavelengths in nm.
        """
        return tuple(map(float, self.query('V ?').split()[2:4]))

    wavelength_range = property(get_wavelength_range)
    wl_range = wavelength_range

    def get_qt_ui(self):
        """Return a Qt control widget bound to this instrument.

        Returns:
            VariSpecUI: A control box for adjusting wavelength and resetting errors.
        """
        return VariSpecUI(self)


class VariSpecUI(QuickControlBox):
    """Qt control box for a :class:`VariSpec` filter (wavelength spinbox, reset button)."""

    def __init__(self, instr):
        """Build the control box and auto-connect its widgets to the instrument.

        Args:
            instr (VariSpec): The filter instrument to control.
        """
        super().__init__()
        self.instr = instr
        self.add_doublespinbox('wavelength', *instr.get_wavelength_range())
        self.add_button('reset_error')
        self.auto_connect_by_name(controlled_object=instr)


if __name__ == '__main__':
    vs = VariSpec('COM13')
    # def loop_wavelength(self, startwl, stopwl, steps, cycles, time):
    #     if(startwl<stopwl) and start>500 and stopwl < 700:
    #         self.write("%s", startwl)
    #         wl = (stopwl-startwl)/steps
    #         for i in range(steps):
    #                 wl_new = startwl+wl*steps
    #                 if(wl_new < 700):
    #                     self.write("w %s \r", wl_new)
    #                 else:
    #                     print("wavelength outside of acceotable range", wl_new)
    #     else:
    #         print("invalid wavelength selected")
