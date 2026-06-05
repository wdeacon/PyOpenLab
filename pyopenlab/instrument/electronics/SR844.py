# -*- coding: utf-8 -*-
"""VISA driver for the Stanford Research Systems SR844 lock-in amplifier."""

from time import sleep

import numpy as np

import pyopenlab.instrument.visa_instrument as vi


class Lockin_SR844(vi.VisaInstrument):
    """Software control for the Stanford Research Systems SR844 lock-in."""

    def __init__(self, address='GPIB0::8::INSTR'):
        """Set up VISA communication and the value-translation dictionaries.

        The dictionaries translate between the integer codes the lock-in
        sends/receives and real-world values, for channel number, sensitivity,
        time constant and filter options.

        Args:
            address: VISA resource address.
        """
        super(Lockin_SR844, self).__init__(address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = None
        print(self.instr.read_termination)

        print(self.write("OUTX"))

        self.ch_list = {
            'X': 1,
            'Y': 2,
            'R[V]': 3,
            'R [dBm]': 4,
            "theta": 5,
            "AUX1": 6,
            "AUX2": 7,
            "Ref Freq": 8,
            "CH1": 9,
            "CH2": 10}
        self.sens_list = {
            0: 100E-9,
            1: 300E-9,
            2: 1E-6,
            3: 3E-6,
            4: 10E-6,
            5: 30E-6,
            6: 100E-6,
            7: 300E-6,
            8: 1E-3,
            9: 3E-3,
            10: 10E-3,
            11: 30E-3,
            12: 100E-3,
            13: 300E-3,
            14: 1}
        self.time_list = {
            0: 100E-6,
            1: 300E-6,
            2: 1E-3,
            3: 3E-3,
            4: 10E-3,
            5: 30E-3,
            6: 100E-3,
            7: 300E-3,
            8: 1,
            9: 3,
            10: 10,
            11: 30,
            12: 100,
            13: 300,
            14: 1E3,
            15: 3E3,
            16: 10E3,
            17: 30E3}
        self.filter_list = {0: "No Filter", 1: "6 dB", 2: "12 dB", 3: "24 dB"}

    def measure_variables(self, channels="1,2"):
        """Upto six variable read, must be greater than 1 measure via a string
        Args:
            channels(str):  A string containing integers seperated by a comma 
                            refering to each of the Variable that you which to 
                            measure (as shown below):
                            1   X
                            2   Y
                            3   R [V]
                            4   R [dBm]
                            5   θ
                            6   AUX IN 1
                            7   AUX IN 2
                            8   Reference Frequency
                            9   CH1 display
                            10  CH2 display 
        """
        variables = self.query("SNAP? " + channels)
        variables = variables.split(",")
        variables = [float(i) for i in variables]
        return variables

    def measure_X(self):
        """Measure the in-phase component X (offsets and ratio applied).

        Returns:
            float: The current X value.
        """
        return self.float_query("OUTP? 1")

    def measure_Y(self):
        """Measure the quadrature component Y (offsets and ratio applied).

        Returns:
            float: The current Y value.
        """
        return self.float_query("OUTP? 2")

    def measure_R(self):
        """Measure the magnitude R (offsets and ratio applied).

        Returns:
            float: The current R value.
        """
        output = -1
        while output > 1 or output < 0:
            output = self.float_query("OUTP? 3")
        return self.float_query("OUTP? 3")

    def measure_theta(self):
        """Measure the phase theta (offsets and ratio applied).

        Returns:
            float: The current phase value.
        """
        return self.float_query("OUTP? 5")

    def check_frequency(self):
        """Read the current reference frequency.

        Returns:
            float: The measurement frequency in Hz.
        """
        return self.float_query("FREQ?")

    def get_sens(self):
        """Read the current sensitivity (backs the ``sensitivity`` property).

        Returns:
            tuple: ``(num, value)`` — the integer index reported by the lock-in
            and the corresponding sensitivity in Vrms from ``self.sens_list``.
        """
        num = self.int_query("SENS?")
        return num, self.sens_list[num]

    def set_sens(self, i):
        """Set the sensitivity by integer index.

        Args:
            i: Sensitivity index, from 0 (100 nVrms / -127 dBm) up to 14
                (1 Vrms / +13 dBm); see ``self.sens_list``.
        """
        self.write("SENS%s" % i)

    sensitivity = property(get_sens, set_sens)
    """tuple: Sensitivity as an ``(index, Vrms)`` pair; set with an integer index."""

    def get_time_costant(self):
        """Read the current time constant (backs ``time_constant``).

        Returns:
            tuple: ``(num, value)`` — the integer index reported by the lock-in
            and the corresponding time constant in seconds from
            ``self.time_list``.
        """
        num = self.int_query("OFLT?")
        return num, self.time_list[num]

    def set_time_costant(self, i):
        """Set the time constant by integer index.

        Args:
            i: Time-constant index, from 0 (100 us) up to 17 (30 ks); see
                ``self.time_list``.
        """
        self.write("OFLT" + str(i))

    time_constant = property(get_time_costant, set_time_costant)
    """tuple: Time constant as an ``(index, seconds)`` pair; set with an integer index."""

    def set_time_constant_from_int(self, integrationtime):
        '''Command to reverse read a dictionary and set the time_constant
        
        Args:
            integrationtime(float):     The real value for the time constant in seconds
                                        for allowed values see self.time_list
        '''
        for i in range(len(list(self.time_list.values())[:])):
            if list(self.time_list.values())[i] == integrationtime:
                self.time_constant = list(self.time_list.keys())[i]
                return True
        print('Setting integration time failed. ' + str(integrationtime) +
              ' is not in self.time_list')
        return False

    def get_filter(self):
        """Read the current filter slope (backs ``filterslope``).

        Returns:
            tuple: ``(num, value)`` — the integer index reported by the lock-in
            and the corresponding filter description from ``self.filter_list``.
        """
        num = self.int_query("OFSL?")
        return num, self.filter_list[num]

    def set_filter(self, i):
        """Set the low-pass filter slope by integer index.

        Args:
            i: Filter index: 0 (no filter), 1 (6 dB), 2 (12 dB), 3 (24 dB);
                see ``self.filter_list``.
        """
        self.write("OFSL%s" % i)

    filterslope = property(get_filter, set_filter)
    """tuple: Filter slope as an ``(index, description)`` pair; set with an integer index."""

    def get_close_res(self):
        """Read the close dynamic reserve (backs ``close_res``).

        Returns:
            int: The close reserve: 0 (high), 1 (normal), 2 (low noise).
        """
        return self.int_query("CRSV?")

    def set_close_res(self, i):
        """Set the close dynamic reserve.

        Args:
            i: Reserve index: 0 (high), 1 (normal), 2 (low noise).
        """
        self.write("CRSV%s" % i)

    close_res = property(get_close_res, set_close_res)

    def get_wide_res(self):
        """Read the wide dynamic reserve (backs ``wide_res``).

        Returns:
            int: The wide reserve: 0 (high), 1 (normal), 2 (low noise).
        """
        return self.int_query("WRSV?")

    def set_wide_res(self, i):
        """Set the wide dynamic reserve.

        Args:
            i: Reserve index: 0 (high), 1 (normal), 2 (low noise).
        """
        self.write("WRSV%s" % i)

    wide_res = property(get_wide_res, set_wide_res)

    def autosens(self):
        '''checks measurement is with range and auto changes sensitivty and reserve respectively
        Returns:
            sens(i,float):  The new sensitivty in both forms
            wide_res(int):  The new wide reserve (high = 0, normal = 1, low noise = 2)
            close_res(int): The new close reserve (high = 0, normal = 1, low noise = 2)
        '''
        testmax = np.max([
            np.abs(self.measure_R()),
            np.abs(self.measure_X()),
            np.abs(self.measure_Y())])
        try:
            Lowersense = self.sens_list[self.sensitivity[0] - 1]
        except KeyError:
            Lowersense = 0.0
        while testmax > self.sensitivity[1] or testmax < Lowersense:
            testmax = np.max([
                np.abs(self.measure_R()),
                np.abs(self.measure_X()),
                np.abs(self.measure_Y())])
            try:
                Lowersense = self.sens_list[self.sensitivity[0] - 1]
            except KeyError:
                Lowersense = 0.0
            if testmax > self.sensitivity[1]:
                if self.sensitivity[0] == 14:
                    print("OVERLOADED RUNNNNNN")
                self.sensitivity = self.sensitivity[0] + 1
            elif testmax < Lowersense:
                self.sensitivity = self.sensitivity[0] - 1
            sleep(1)
            self.write("AWRS")  #wideband reseve
            wide_res = self.wide_res
            self.write("ACRS")  #close in  reseve
            close_res = self.close_res
        sens = self.sensitivity
        wide_res = self.wide_res
        close_res = self.close_res
        return sens, wide_res, close_res

    # else:
    #  print "Measurement within range"

    def set_phase(self, phase=0):
        """Set the reference phase shift in degrees.

        Args:
            phase: Phase shift in degrees.
        """
        self.write("PHAS" + str(phase))


if __name__ == '__main__':
    testlockin = Lockin_SR844()
