# -*- coding: utf-8 -*-
"""VISA driver for the Stanford Research Systems SR810 lock-in amplifier."""
from time import sleep

import numpy as np
import pyvisa

import pyopenlab.instrument.visa_instrument as vi


class Lockin_SR810(vi.VisaInstrument):
    """Software control for the Stanford Research Systems SR810 lock-in."""

    def __init__(self, address='GPIB0::8::INSTR'):
        """Sets up visa communication and class dictionaries
        
        The class dictionaries are manully inputed translations between what 
        the lockin will send/recieve and the real values. 
        These have been built for:
            - channel number i.e. X,Y ...   
            - Sensitivity i.e. Voltage range
            - time constant i.e. integration time
            - Filter options i.e. 6 dB etc
            
        Args:
            address(str):   Visa address
        
        """
        super(Lockin_SR810, self).__init__(address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = None
        print(self.instr.read_termination)
        print(self.write('OUTX'))
        self.write('ICPL 0')
        self.ch_list = {}
        self.sens_list = {}
        self.time_list = {
            0: 10e-6,  # time constant given in sec
            1: 30e-6,
            2: 100e-6,
            3: 300e-6,
            4: 1e-3,
            5: 3e-3,
            6: 0.01,
            7: 0.03,
            8: 0.1,
            9: 0.300,
            10: 1,
            11: 3,
            12: 10,
            13: 30,}
        self.filter_list = {}
        print('lockin connected successfully')
        return

    def measure_variables(self, channels='1,2'):
        """Upto six variable read, must be greater than 1 measure via a string
        Args:
            channels(str):  A string containing integers seperated by a comma 
                            refering to each of the Variable that you which to 
                            measure (as shown below):
                            1   X
                            2   Y
                            3   R [V]
                            4   R [dBm]
                            5   \xce\xb8
                            6   AUX IN 1
                            7   AUX IN 2
                            8   Reference Frequency
                            9   CH1 display
                            10  CH2 display 
        """
        variables = self.query('SNAP? ' + channels)
        variables = variables.split(',')
        variables = [float(i) for i in variables]
        return variables

    def measure_X(self):
        """Measure the in-phase component X (offsets and ratio applied).

        Returns:
            float: The current X value.
        """
        return self.float_query('OUTP? 1')

    def measure_Y(self):
        """Measure the quadrature component Y (offsets and ratio applied).

        Returns:
            float: The current Y value.
        """
        return self.float_query('OUTP? 2')

    def measure_R(self):
        """Measure the magnitude R (offsets and ratio applied).

        Returns:
            float: The current R value.
        """
        output = -1
        while output > 1 or output < 0:
            output = self.float_query('OUTP? 3')

        return self.float_query('OUTP? 3')

    def measure_theta(self):
        """Measure the phase theta (offsets and ratio applied).

        Returns:
            float: The current phase value.
        """
        return self.float_query('OUTP? 4')

    def check_frequency(self):
        """Read the current reference frequency.

        Returns:
            float: The measurement frequency in Hz.
        """
        return self.float_query('FREQ?')

    def get_sens(self):
        """Read the current sensitivity (backs the ``sensitivity`` property).

        Returns:
            tuple: ``(num, value)`` — the integer index reported by the lock-in
            and the corresponding sensitivity in Vrms from ``self.sens_list``.
        """
        num = self.int_query('SENS?')
        return (num, self.sens_list[num])

    def set_sens(self, i):
        """Set the sensitivity by integer index.

        Args:
            i: Sensitivity index, increasing from the most to least sensitive
                voltage range; see ``self.sens_list`` for the mapping.
        """
        self.write('SENS%s' % i)

    sensitivity = property(get_sens, set_sens)
    """tuple: Sensitivity as an ``(index, Vrms)`` pair; set with an integer index."""

    def get_time_constant(self):
        """Read the current time constant (backs ``time_constant``).

        Returns:
            tuple: ``(num, value)`` — the integer index reported by the lock-in
            and the corresponding time constant in seconds from
            ``self.time_list``.
        """
        num = self.int_query('OFLT?')
        return (num, self.time_list[num])

    def set_time_constant(self, i):
        """Set the time constant by integer index.

        Args:
            i: Time-constant index, from 0 (10 us) up to 13 (30 s); see
                ``self.time_list``.
        """
        self.write('OFLT' + str(i))

    time_constant = property(get_time_constant, set_time_constant)
    """tuple: Time constant as an ``(index, seconds)`` pair; set with an integer index."""

    def set_time_constant_from_int(self, integrationtime):
        """Command to reverse read a dictionary and set the time_constant
        
        Args:
            integrationtime(float):     The real value for the time constant in seconds
                                        for allowed values see self.time_list
        """
        for i in range(len(list(self.time_list.values())[:])):
            if list(self.time_list.values())[i] == integrationtime:
                self.time_constant = list(self.time_list.keys())[i]
                return True

        print('Setting integration time failed. ' + str(integrationtime) +
              ' is not in self.time_list')
        return False

    def get_line_filter(self):
        """ Gets filter related to power line, 
            0 - no filter
            1 - line filter
            2 - 2xline filter
            3 - Both """
        num_filter = self.int_query('ILIN?')
        return num_filter

    def set_line_filter(self, filter_mode):
        """ Sets filter related to power line, 
            0 - no filter
            1 - line filter
            2 - 2xline filter
            3 - Both """
        self.write('ILIN' + str(filter_mode))

    linefilter = property(get_line_filter, set_line_filter)

    def set_input_mode(self, mode):
        """Sets the input mode:
            A (i=0), A-B (i=1), I (1 M\xce\xa9) (i=2) or I (100 M\xce\xa9) (i=3)."""
        self.write('ISRC' + str(mode))

    def get_input_mode(self):
        """Read the input configuration index (backs ``inputmode``).

        Returns:
            int: 0 (A), 1 (A-B), 2 (I, 1 MOhm) or 3 (I, 100 MOhm).
        """
        return self.int_query('ISRC?')

    inputmode = property(get_input_mode, set_input_mode)

    def get_filter(self):
        """Read the current filter slope (backs ``filterslope``).

        Returns:
            tuple: ``(num, value)`` — the integer index reported by the lock-in
            and the corresponding filter description from ``self.filter_list``.
        """
        num = self.int_query('OFSL?')
        return (num, self.filter_list[num])

    def set_filter(self, i):
        """Set the low-pass filter slope by integer index.

        Args:
            i: Filter index: 0 (no filter), 1 (6 dB), 2 (12 dB), 3 (18 dB),
                4 (24 dB).
        """
        self.write('OFSL%s' % i)

    filterslope = property(get_filter, set_filter)
    """tuple: Filter slope as an ``(index, description)`` pair; set with an integer index."""

    def get_res(self):
        """ Gets the dynamic reserve of the lockin
         0 = High, 1 = normal, 2 = low noise
        """
        return self.int_query('RMOD?')

    def set_res(self, i):
        """Set the dynamic reserve: 0 (high), 1 (normal), 2 (low noise)."""
        self.write('RMOD%s' % i)

    reserve = property(get_res, set_res)

    def set_phase(self, phase):
        """Set the reference phase shift in degrees.

        Args:
            phase: Phase shift in degrees.
        """
        self.write('PHAS' + str(phase))

    def get_phase(self):
        """Read the reference phase shift.

        Returns:
            float: The phase shift in degrees.
        """
        return self.float_query('PHAS?')

    phase = property(get_phase, set_phase)

    def autosens(self):
        """checks measurement is with range and auto changes sensitivty and reserve respectively
        Returns:
            sens(i,float):  The new sensitivty in both forms
            wide_res(int):  The new wide reserve (high = 0, normal = 1, low noise = 2)
            close_res(int): The new close reserve (high = 0, normal = 1, low noise = 2)
        """
        testmax = np.max([
            np.abs(self.measure_R()),
            np.abs(self.measure_X()),
            np.abs(self.measure_Y())])
        try:
            Lowersense = self.sens_list[(self.sensitivity[0] - 1)]
        except KeyError:
            Lowersense = 0.0
        else:
            while testmax > self.sensitivity[1] or testmax < Lowersense:
                testmax = np.max([
                    np.abs(self.measure_R()),
                    np.abs(self.measure_X()),
                    np.abs(self.measure_Y())])
                try:
                    Lowersense = self.sens_list[(self.sensitivity[0] - 1)]
                except KeyError:
                    Lowersense = 0.0
                else:
                    if testmax > self.sensitivity[1]:
                        if self.sensitivity[0] == 14:
                            print('OVERLOADED RUNNNNNN')
                        self.sensitivity = self.sensitivity[0] + 1
                    elif testmax < Lowersense:
                        self.sensitivity = self.sensitivity[0] - 1
                    sleep(1)
                    self.write('AWRS')
                    wide_res = self.wide_res
                    self.write('ACRS')
                    close_res = self.close_res

        sens = self.sensitivity
        wide_res = self.wide_res
        close_res = self.close_res
        return (sens, wide_res, close_res)

    def get_harmonic(self):
        """Read the detection harmonic (backs ``harmonic``).

        Returns:
            int: The harmonic number currently detected.
        """
        num = self.int_query("HARM?")
        return num

    def set_harmonic(self, i):
        """Set the detection harmonic.

        Args:
            i: Harmonic number to detect.
        """
        self.write("HARM%s" % i)

    harmonic = property(get_harmonic, set_harmonic)


if __name__ == '__main__':
    #testlockin = Lockin_SR844()
    testlockin = Lockin_SR810(address='GPIB0::8::INSTR')
# okay decompiling SR810.pyc
