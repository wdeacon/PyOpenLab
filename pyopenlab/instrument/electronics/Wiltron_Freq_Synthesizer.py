# -*- coding: utf-8 -*-
"""VISA driver for the Wiltron 6769B swept frequency synthesizer."""
from time import sleep

import numpy as np
import pyvisa

import pyopenlab.instrument.visa_instrument as vi


class freq_source(vi.VisaInstrument):
    """Software control for the Wiltron 6769B swept frequency source."""

    def __init__(self, address='GPIB0::5::INSTR'):
        """Open VISA communication with the synthesizer.

        Args:
            address: VISA resource address.
        """
        super(freq_source, self).__init__(address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = 1
        print(self.query('OI'))
        print('source connected successfully')
        return

    def set_freq(self, mem_slot=1, target_freq=2.2):
        """Store a frequency in a preset memory slot.

        Args:
            mem_slot: Preset memory slot, 1-9.
            target_freq: Frequency in GHz.
        """
        self._write('F' + str(mem_slot) + str(target_freq) + 'GH')
        return

    def RF_on(self):
        """Enable the RF output."""
        self._write('RF1')

    def RF_off(self):
        """Disable the RF output."""
        self._write('RF0')

    def set_power(self, power=-10):
        """Set the output power.

        Args:
            power: Output power in dBm.
        """
        self._write('L1' + str(power) + 'DM')

    def get_power(self):
        """Query the output power level.

        Returns:
            The instrument's power level response.
        """
        return self.query('OL1')

    def close(self):
        """Close the VISA connection."""
        self.instr.close()

    def freq_sweep(self, f1=2.1, f2=2.5, T=30):
        """Sweep the frequency from ``f1`` to ``f2`` over time ``T``.

        Args:
            f1: Start frequency in GHz (stored in slot 1).
            f2: Stop frequency in GHz (stored in slot 2).
            T: Sweep time in seconds.
        """
        self.set_freq(mem_slot=2, target_freq=f2)
        self.set_freq(mem_slot=1, target_freq=f1)
        self._write('SWT' + str(T) + 'SEC')  #set scan time to 30sec
        self._write('SF1')  # start scan

    def set_cw(self, mem_slot=1, freq=2.1):
        """Set a fixed continuous-wave output frequency.

        Args:
            mem_slot: Preset memory slot to use, 1-9.
            freq: CW frequency in GHz.
        """
        self.set_freq(mem_slot=mem_slot, target_freq=freq)
        self._write('CF1')

    def AM_on(self):
        """Enable amplitude modulation."""
        self._write('AM1')

    def AM_off(self):
        """Disable amplitude modulation."""
        self._write('AM0')

    def FM_on(self):
        """Enable frequency modulation."""
        self._write('FM1')

    def FM_off(self):
        """Disable frequency modulation."""
        self._write('FM0')


if __name__ == '__main__':
    source = freq_source(address='GPIB0::5::INSTR')
