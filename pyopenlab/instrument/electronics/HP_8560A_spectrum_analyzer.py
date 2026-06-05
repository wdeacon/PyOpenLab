# -*- coding: utf-8 -*-
"""VISA driver for the HP 8560A RF spectrum analyzer."""

from functools import partial
from time import sleep

import matplotlib.pyplot as plt
import numpy as np

from pyopenlab.instrument.visa_instrument import queried_property
from pyopenlab.instrument.visa_instrument import VisaInstrument


class SpectrumAnalyzer(VisaInstrument):
    """Control for the HP 8560A spectrum analyzer."""

    def __init__(self, address='GPIB0::18::INSTR'):
        """Open VISA communication with the analyzer.

        Args:
            address: VISA resource address.
        """
        super(SpectrumAnalyzer, self).__init__(address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.freq_points = 601

    # frequency = queried_property('freq?', 'freq {0}')
    # function = queried_property('function:shape?', 'function:shape {0}',
    #                             validate=['sinusoid', 'dc'], dtype='str')
    # voltage = queried_property('voltage?', 'voltage {0}')
    # offset = queried_property('voltage:offset?', 'voltage:offset {0}')
    # output_load = queried_property('output:load?', 'output:load {0}',
    #                                validate=['inf'], dtype='str')
    # volt_high = queried_property('volt:high?', 'volt:high {0}')
    # volt_low = queried_property('volt:low?', 'volt:low {0}')
    # output = queried_property('output?', 'output {0}',
    #                           validate=['OFF', 'ON'], dtype='str')

    def reset(self):
        """Reset the analyzer to its default state (``*RST``)."""
        self.write('*rst')

    def get_center_freq(self):
        """Return the centre frequency in MHz."""
        return float(self.query('CF?')) / 1e6  #return span in MHz

    def set_center_freq(self, CF):
        """Set the centre frequency.

        Args:
            CF: Centre frequency in Hz.

        Returns:
            float: The centre frequency read back, in kHz.
        """
        self.write('CF ' + str(CF) + ' HZ')
        return float(self.query('CF?')) / 1e3  #return span in kHz

    def get_span(self):
        """Return the frequency span in kHz."""
        return float(self.query('SP?')) / 1e3  #return span in kHz

    def set_span(self, SP):
        """Set the frequency span.

        Args:
            SP: Span in Hz.

        Returns:
            float: The span read back, in kHz.
        """
        self.write('SP ' + str(SP) + ' HZ')
        return float(self.query('SP?')) / 1e3  #return span in kHz

    def get_res(self):
        """Return the resolution bandwidth in kHz."""
        return float(self.query('RB?')) / 1e3  # returns resolution in MHz

    def set_res(self, res):
        """Set the resolution bandwidth.

        Args:
            res: Resolution bandwidth in Hz.

        Returns:
            float: The resolution bandwidth read back, in kHz.
        """
        self.write('RB ' + str(res) + ' HZ')
        return float(self.query('RB?')) / 1e3  #return span in MHz

    def get_sweep_time(self):
        """Return the sweep time in seconds."""
        return float(self.query('ST?'))  #return sweep time in sec

    def set_sweep_time(self, ST):
        """Set the sweep time.

        Args:
            ST: Sweep time in seconds.

        Returns:
            float: The sweep time read back, in seconds.
        """
        self.write('ST ' + str(ST) + ' S')
        sleep(1)
        return float(self.query('ST?'))  #return span in MHz

    def set_single_sweep(self):
        """Put the analyzer into single-sweep mode."""
        self.write('SNGLS')

    def set_cont_sweep(self):
        """Put the analyzer into continuous-sweep mode."""
        self.write('CONTS')

    def command_completed(self):
        """Block until the analyzer reports the current operation is done.

        Returns:
            bool: True once ``DONE?`` returns truthy.
        """
        done = False
        while not done:
            try:
                done = bool(self.query('DONE?'))
            except:
                done = False
        return done

    # def take_sweep(self):

    #     self.write('TS')
    #     done=False
    #     while not done:
    #         try:
    #             done=bool(self.query('DONE?'))
    #         except:
    #             done=False
    #     print('sweep ended')
    #     return True

    def take_sweep(self):
        """Trigger a sweep and wait for it to complete.

        Returns:
            bool: True if the sweep completed.
        """
        self.write('TS')
        if self.command_completed():
            print('sweep completed')
            return True

    def get_data(self):
        """Read the current trace data.

        Returns:
            ndarray: The trace amplitudes.
        """
        self.clear_read_buffer()
        data = self.query('TRA?')
        data = np.fromstring(data, dtype=float, sep=',')
        return (data)

    def get_freq_axis(self):
        """Build the frequency axis for the current span.

        Returns:
            ndarray: ``freq_points`` frequencies in MHz from start to stop.
        """
        fa = float(self.query('FA?')) / 1e6
        fb = float(self.query('FB?')) / 1e6
        return np.linspace(fa, fb, self.freq_points)


#%% make instrument
if __name__ == '__main__':
    SA = SpectrumAnalyzer(address='GPIB0::18::INSTR')
    SA.clear_read_buffer()
    print('center freq: ' + str(SA.get_center_freq()))
    print('sweep span: ' + str(SA.get_span()))
    print('sweep time: ' + str(SA.get_sweep_time()))
    #SA.take_sweep()
    # data=SA.get_data()
    # f=SA.get_freq_axis()
    # plt.figure()
    # plt.plot(f,data)
