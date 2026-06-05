# -*- coding: utf-8 -*-
"""VISA driver for the Agilent E3631A triple-output DC power supply.

Note:
    The per-channel voltage/current methods (``set_voltage``, ``get_voltage``,
    ``set_current``, ``get_current``, ``measure_voltage``, ``measure_current``)
    refer to a module-level ``S`` rather than ``self`` and will raise
    ``NameError`` unless such a global exists. This is a pre-existing bug left
    for a later code pass; the docstrings below describe the intended behavior.
"""

from functools import partial
from time import sleep

import matplotlib.pyplot as plt
import numpy as np

from pyopenlab.instrument.visa_instrument import queried_property
from pyopenlab.instrument.visa_instrument import VisaInstrument


class PowerSupply(VisaInstrument):
    """Control for the Agilent E3631A triple-output DC power supply."""

    def __init__(self, address='GPIB0::5::INSTR'):
        """Open VISA communication with the power supply.

        Args:
            address: VISA resource address.
        """
        super(PowerSupply, self).__init__(address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'

    def reset(self):
        """Reset the supply to its default state (``*RST``)."""
        self.write('*rst')

    def output_is_on(self):
        """Return the output enable state as reported by the supply."""
        return self.query('OUTP:STAT?')

    def output_on(self):
        """Enable the supply output."""
        return self.write('OUTPUT ON')

    def output_off(self):
        """Disable the supply output."""
        return self.write('OUTPUT OFF')

    def operation_complete(self):
        """Return True once pending operations finish (``*OPC?``)."""
        return bool(self.query('*OPC?'))

    def clear_errors(self):
        """Drain the error queue, printing each entry until it is empty."""
        is_error = True
        while is_error:
            ans = self.query('SYST:ERR?')
            print(ans)
            if ans == '+0,"No error"':
                is_error = False
        print('error cleared')

    def set_channel(self, channel=1):
        """Select the active output channel.

        Args:
            channel: 1 (+6 V), 2 (+25 V) or 3 (-25 V).
        """
        if channel in [1, 2, 3]:
            self.write('instrument:nselect ' + str(channel))
        else:
            print(' channel has to be 1/2/3')

    def get_channel(self):
        """Return the active channel number: 1 (+6 V), 2 (+25 V), 3 (-25 V)."""
        return self.float_query('instrument:nselect?')

    def set_voltage(self, value=0.5):
        """Set the output voltage of the active channel, within its limits.

        Args:
            value: Target voltage in volts. Ignored (with a message) if outside
                the active channel's range.
        """
        channel = S.int_query('instrument:nselect?')
        if channel == 1:
            ulim = 6
            llim = 0
        if channel == 2:
            ulim = 25
            llim = 0
        if channel == 3:
            ulim = 0
            llim = -25
        if value < llim or value > ulim:
            print('value out of channel limits')
        else:
            S.write('voltage ' + str(value))

    def get_voltage(self):
        """Return the voltage setpoint of the active channel."""
        return S.float_query('voltage?')

    def measure_voltage(self):
        """Measure the actual output voltage of the active channel."""
        return S.float_query('measure:voltage?')

    def set_current(self, value=0.01):
        """Set the output current limit of the active channel, within its range.

        Args:
            value: Target current in amps. Ignored (with a message) if outside
                the active channel's range.
        """
        channel = S.int_query('instrument:nselect?')
        if channel == 1:
            ulim = 5
            llim = 0
        if channel == 2:
            ulim = 1
            llim = 0
        if channel == 3:
            ulim = 1
            llim = 0
        if value < llim or value > ulim:
            print('value out of channel limits')
        else:
            S.write('current ' + str(value))

    def get_current(self):
        """Return the current setpoint of the active channel."""
        return S.float_query('current?')

    def measure_current(self):
        """Measure the actual output current of the active channel."""
        return S.float_query('measure:current?')

    def set_channel_values(self, channel=1, voltage=2, current=0.05):
        """Select a channel and set both its voltage and current.

        Args:
            channel: Channel to configure (1, 2 or 3).
            voltage: Voltage setpoint in volts.
            current: Current limit in amps.
        """
        self.set_channel(channel)
        self.set_current(current)
        self.set_voltage(voltage)

    def get_channel_values(self):
        """Print the active channel's set and measured voltage and current."""
        channel = self.get_channel()
        set_voltage_value = self.get_voltage()
        measured_voltage_value = self.measure_voltage()
        set_current_value = self.get_current()
        measured_current_value = self.measure_current()
        print('channel ' + str(channel))
        print('set voltage is ' + str(set_voltage_value) + 'V')
        print('measured voltage is ' + str(measured_voltage_value) + 'V')
        print('set current is ' + str(set_current_value) + 'A')
        print('measured current is ' + str(measured_current_value) + 'A')

    def increase_voltage(self, step_size=0.05, print_flag=True):
        """Increase the active channel's voltage by ``step_size`` volts.

        Args:
            step_size: Increment in volts.
            print_flag: If True, print the channel values before and after.
        """
        if print_flag:
            self.get_channel_values()
        v = self.get_voltage()
        self.set_voltage(v + step_size)
        if print_flag:
            print('new values are:\n')
            self.get_channel_values()

    def decrease_voltage(self, step_size=0.05, print_flag=True):
        """Decrease the active channel's voltage by ``step_size`` volts.

        Args:
            step_size: Decrement in volts.
            print_flag: If True, print the channel values before and after.
        """
        if print_flag:
            self.get_channel_values()
        v = self.get_voltage()
        self.set_voltage(v - step_size)
        if print_flag:
            print('new values are:\n')
            self.get_channel_values()


#%% make instrument
if __name__ == '__main__':
    S = PowerSupply(address='GPIB1::5::INSTR')
