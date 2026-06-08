"""VISA control of an acousto-optic modulator (AOM) driven via a function generator's DC offset."""

import time

import numpy as np
import pyvisa as visa

from pyopenlab.instrument.visa_instrument import VisaInstrument


def Sigmoid(x, Shift=0.68207277, Scale=8.49175969):
    """Map an input to a normalised sigmoid response.

    Args:
        x (float or numpy.ndarray): Input value(s).
        Shift (float): Horizontal shift (centre) of the sigmoid.
        Scale (float): Steepness of the sigmoid.

    Returns:
        float or numpy.ndarray: The sigmoid response rescaled so the endpoints map to 0 and 1.
    """
    Zero = 1. / (np.exp(Shift * Scale) + 1)
    One = 1. / (np.exp(-(1 - Shift) * Scale) + 1)

    Output = (x - Shift) * Scale
    Output = np.exp(-Output) + 1
    Output = 1. / Output
    return (Output - Zero) / (One - Zero)


def Inverse_Sigmoid(x, Shift=0.68207277, Scale=8.49175969):
    """Invert :func:`Sigmoid`, mapping a normalised response back to its input.

    Args:
        x (float or numpy.ndarray): Normalised response value(s) in ``[0, 1]``.
        Shift (float): Horizontal shift (centre) of the sigmoid.
        Scale (float): Steepness of the sigmoid.

    Returns:
        float or numpy.ndarray: The input that :func:`Sigmoid` would map to ``x``.
    """
    Zero = 1. / (np.exp(Shift * Scale) + 1)
    One = 1. / (np.exp(-(1 - Shift) * Scale) + 1)

    Output = -np.log((1. / (((One - Zero) * x) + Zero)) - 1)
    Output /= Scale
    Output += Shift
    return Output


class AOM(VisaInstrument):
    """Acousto-optic modulator controlled through a function generator's DC offset voltage.

    Note:
        :meth:`Find_Power` appends ``Power_Meter.read`` (the bound method object) instead of calling
        it, so the readings are not real measurements; the search will not converge as intended.
    """

    def __init__(self, address='USB0::0x0957::0x0407::MY44037993::0::INSTR', *args, **kwargs):
        """Connect to the function generator and configure it for DC output.

        Args:
            address (str): VISA resource address of the function generator.
            *args: Forwarded to :class:`VisaInstrument`.
            **kwargs: Forwarded to :class:`VisaInstrument`.
        """
        super().__init__(address, *args, **kwargs)
        self.Power_Supply = self.instr
        self.mode = 'R'

        self.Power_Supply.write("FUNC DC")
        self.Power_Supply.write("VOLT:OFFS 1")

    def Switch_Mode(self):
        """Toggle between remote (``'R'``) and local (``'L'``) front-panel control modes."""
        if self.mode == 'R':
            self.mode = 'L'
        else:
            self.mode = 'R'

    @property
    def mode(self):
        """str: Control mode, ``'R'`` for remote or ``'L'`` for local front-panel control."""
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
        out = 'SYSTEM:'
        if value == 'R':
            out += 'REMOTE'
        else:
            out += 'LOCAL'
        self.Power_Supply.write(out)

    def Power(self, Fraction=None):
        """Get or set the AOM drive level via the function generator's DC offset voltage.

        Args:
            Fraction (float, optional): If None, query and return the current offset voltage.
                Otherwise, set the offset voltage, clamped to ``[0, 1]``.

        Returns:
            float or None: The current offset voltage when querying; None when setting.
        """
        #        if Fraction is None:
        #            Voltage=float(self.Power_Supply.query("SOUR:VOLT:OFFS?"))
        #            return Inverse_Sigmoid(Voltage)
        #        else:
        #            if Fraction<0:
        #                Fraction=0.
        #            if Fraction>1:
        #                Fraction=1.
        #            Voltage=Sigmoid(Fraction)
        #            self.Power_Supply.write("VOLT:OFFS "+str(Voltage))
        #
        if Fraction is None:
            return float(self.Power_Supply.query("SOUR:VOLT:OFFS?"))
        else:
            if Fraction < 0:
                Fraction = 0.
            if Fraction > 1:
                Fraction = 1.
            self.Power_Supply.write("VOLT:OFFS " + str(Fraction))

    def Get_Power(self):
        """Query the current DC offset voltage.

        Returns:
            float: The current offset voltage.
        """
        return float(self.Power_Supply.query("SOUR:VOLT:OFFS?"))

    def Power_Apply(self, shape, frequency, amplitude, offset):
        """Configure the function generator output waveform.

        Args:
            shape (str): Waveform shape keyword (e.g. ``'SIN'``, ``'SQU'``).
            frequency (float): Frequency in Hz.
            amplitude (float): Peak-to-peak amplitude in volts.
            offset (float): DC offset in volts.
        """
        self.Power_Supply.write("APPL:%s %d Hz, %f VPP, %f V" %
                                (shape, frequency, amplitude, offset))

    def Find_Power(self, Power, Power_Meter, Laser_Shutter, Steps=10, Tolerance=1.):
        """Search for the AOM drive level that produces a target optical power.

        Uses a bisection then linear-interpolation search, opening and closing the laser shutter
        around each power-meter reading.

        Args:
            Power (float): Target optical power in microwatts.
            Power_Meter: Power meter whose ``read`` attribute provides a reading.
            Laser_Shutter: Shutter object with ``open_shutter``, ``close_shutter`` and ``set_mode``.
            Steps (int): Minimum number of interpolation steps to perform.
            Tolerance (float): Acceptable error in microwatts.

        Returns:
            tuple or None: ``(Guess, Reading)`` for the final drive level and its measured power,
            or None if the target is outside the achievable range.

        Raises:
            Exception: If the power meter fails to read ten times in a row.
        """
        Bounds = [0, 1]
        Laser_Shutter.close_shutter()
        Laser_Shutter.set_mode(1)

        def Take_Reading():
            Laser_Shutter.open_shutter()
            Output = []
            Fail = 0
            while len(Output) < 20:
                try:
                    Output.append(Power_Meter.read)
                    Fail = 0
                except:
                    Fail += 1
                if Fail == 10:
                    raise Exception('Restart power meter')
            Laser_Shutter.close_shutter()
            return np.median(Output) * 1000000

        x = [0., 1]
        y = []
        for i in x:
            self.Power(i)
            y.append(Take_Reading())
            time.sleep(1)

        if y[0] > Power or y[1] < Power:
            print('Out of Range!')
            return

        for i in range(2):
            Bound = np.mean(x)
            self.Power(Bound)
            Reading = Take_Reading()
            if Reading > Power:
                x[1] = Bound
                y[1] = Reading
            else:
                x[0] = Bound
                y[0] = Reading
            time.sleep(1)

        Step = 0
        Error = np.inf
        while Step < Steps or Error > Tolerance:
            Step += 1
            print('Error:', str(round(Error, 2)), 'uW')
            if x[1] != x[0]:
                m = (y[1] - y[0]) / (x[1] - x[0])
                c = y[0] - (m * x[0])
                Guess = (Power - c) / m
                self.Power(Guess)
                Reading = Take_Reading()
                Error = np.abs(Reading - Power)
                if Power < Reading:
                    y[1] = Reading
                    x[1] = Guess
                else:
                    y[0] = Reading
                    x[0] = Guess
                time.sleep(1)
            else:
                Step = np.inf
                Error = 0
        if x[1] != x[0]:
            m = (y[1] - y[0]) / (x[1] - x[0])
            c = y[0] - (m * x[0])
            Guess = (Power - c) / m
        else:
            Guess = x[0]
        self.Power(Guess)
        Reading = Take_Reading()
        return Guess, Reading


if __name__ == '__main__':
    aom = AOM('USB0::0x0957::0x0407::MY44037993::0::INSTR')
    aom.Switch_Mode()
