# -*- coding: utf-8 -*-
"""VISA driver for the Thorlabs PM100-series optical power meter."""
import numpy as np

from pyopenlab.instrument.electronics.power_meter import PowerMeter
from pyopenlab.instrument.visa_instrument import VisaInstrument


class ThorlabsPowermeter(PowerMeter, VisaInstrument):
    """Thorlabs PM100 power meter, combining the PowerMeter UI with VISA I/O."""

    def __init__(
            self,
            address='USB0::0x1313::0x807B::201029132::INSTR',
            settings={
                # 'timeout': 0.1,
                'read_termination': '\n',
                'write_termination': '\r\n',}):
        """Open VISA communication and initialise the meter.

        Args:
            address: VISA resource address.
            settings: VISA session settings (read/write terminations, etc.).
        """
        VisaInstrument.__init__(self, address=address, settings=settings)
        PowerMeter.__init__(self)
        self.query("*IDN?")  # Needed the initialise powermeter, apparently(?)
        self.address = address
        self.settings = settings
        self.num_averages = 10

    def _read(self):
        """Read the raw power in watts.

        Returns:
            float: The instantaneous power in watts.
        """
        return float(self.query('READ?'))

    @property
    def wavelength(self):
        """The correction wavelength in nm used for the power calibration."""
        return self.query('Sense:Correction:WAVelength?')

    @wavelength.setter
    def wavelength(self, wl):
        self.write('Sense:Correction:WAVelength ' + str(wl))

    def read_average(self, num_averages=None):
        """Read and average several power measurements.

        Pauses live mode, retries past transient read failures, and returns the
        mean. Gives up after 20 consecutive failures.

        Args:
            num_averages: Number of readings to average; defaults to
                :attr:`num_averages`.

        Returns:
            float: The mean power over the successful readings.
        """
        live = self.live
        self.live = False
        if num_averages is None:
            num_averages = self.num_averages
        powers = []
        failures = 0
        while failures < 20 and len(powers) < num_averages:
            try:
                powers.append(self.power)
                failures = 0
            except:
                failures += 1
        # average = np.mean([self.power for _ in range(num_averages)])
        average = np.mean(powers)
        self.live = live
        return average

    def read_power(self):
        """Read the current power in milliwatts.

        Returns:
            float: The instantaneous power in mW.
        """
        return self._read() * 1000

    def restart(self):
        """Re-open the VISA connection by re-running ``__init__``."""
        self.__init__(self.address)


if __name__ == '__main__':
    import pyvisa as visa
    pm = ThorlabsPowermeter(visa.ResourceManager().list_resources()[0])
    pm.show_gui(blocking=False)
