"""Driver for the Thorlabs ELL18K elliptical motor rotation stage.

Optimised for the revised (2019) hardware revision and performs backlash
correction so that a target angle is always approached from the same side.
"""

import struct

import numpy as np

from pyopenlab.instrument import serial_instrument as serial


class ELL18K(object):

    def __init__(self, Port=None, Backlash_Correct=True):
        """Open the serial port, read the encoder resolution and calibrate.

        The number of counts per revolution varies between hardware iterations
        and so is queried from the device rather than hard-coded.

        Args:
            Port (str): COM port the stage is connected to.
            Backlash_Correct (bool): If True, always approach the target angle
                from the same side to remove mechanical backlash.
        """

        self.Port = serial.SerialInstrument(Port)
        self.Port.open()
        self.Counts_per_Rev = int('0x' + self.Write_Hex('0in')[-9:-2],
                                  0)  #Cuts off return characters
        self.Backlash_Correct = Backlash_Correct

        self.Calibrate_Motors()  #Calibrates motor resonance frequencies to account for load etc.

    #------Utility functions----------

    def Number_to_Hex(self, Input, Min_Digits=8):
        """Convert an integer to an upper-case, zero-padded hex string.

        Args:
            Input (int): Value to convert.
            Min_Digits (int): Minimum string length; the result is left-padded
                with zeros until it reaches this width.

        Returns:
            str: Hex representation without the ``0x`` prefix.
        """
        Hex = str(hex(Input))[2:].upper()  #All letters should be upper case

        while len(Hex) < Min_Digits:
            Hex = '0' + Hex
        return Hex

    def Convert_Status(self, Code):
        """Convert a numeric device status code into a human-readable string.

        Args:
            Code (int): Status code returned by the device.

        Returns:
            str: Description of the status, or a placeholder for codes >= 14.
        """
        Responses = [
            'No Error', 'Communication time out', 'Mechanical time out', 'Command error',
            'Value out of range', 'Module isolated']
        Responses += [
            'Module out of isolation', 'Initializing error', 'Thermal error', 'Busy',
            'Sensor Error', 'Initializing error', 'Thermal error', 'Busy']
        Responses += ['Sensor Error', 'Motor Error', 'Out of Range']

        if Code >= 14:
            return 'Reserved Response Code'
        else:
            return Responses[Code]

    def Write_Hex(self, String):
        """Send a command string to the port and return the device's reply.

        Args:
            String (str): Command to transmit, sent one character at a time.

        Returns:
            str: The line read back from the device.
        """

        Seperate = []
        Format = ''
        for i in String:
            Seperate.append(bytes(i, "utf-8"))
            Format += 'c'
        Packer = struct.Struct(format=Format)
        self.Port.write(Packer.pack(*Seperate))

        Response = self.Port.readline()
        return Response

    def Two_Compliment(self, Integer, Bits=32):
        """Return the two's complement of an integer for a given bit width.

        Used to decode negative positions, which the device reports as large
        unsigned values.

        Args:
            Integer (int): Value to convert.
            Bits (int): Bit width of the representation.

        Returns:
            int: The two's-complement value.
        """
        String = bin(Integer)[2:]
        while len(String) < Bits:
            String = '0' + String
        New = []
        for i in range(len(String)):
            New.append((-1 * (int(String[i]) - 1)))
        n = len(New) - 1
        New[-1] += 1
        while n >= 0:
            if New[n] == 2:
                New[n] = 0
                if n > 0:
                    New[n - 1] += 1
            else:
                n = 0
            n -= 1
        String_New = '0b'
        for i in New:
            String_New += str(i)
        return int(String_New, 0)

    #------Stage Commands----------

    def Calibrate_Motors(self):
        """Sweep both motors to find their optimal resonance frequency.

        Compensates for load and other mechanical variation on the stage.
        """
        self.Write_Hex('0s1')
        self.Write_Hex('0s2')
        self.Write_Hex('0us')

    def Get_Status(self):
        """Request and decode the current device status.

        Returns:
            str: Human-readable status description.
        """
        Status = self.Write_Hex('0gs')
        Code = int('0x' + Status[3:], 0)
        return self.Convert_Status(Code)

    def Read_Position(self, Integer=None):
        """Return the current stage angle in degrees.

        Args:
            Integer (int, optional): A raw motor-step count to convert. If
                None, the count is queried from the device.

        Returns:
            float: Stage angle in degrees, or a status string if the device
            returned a status code instead of a position.
        """
        if Integer is None:
            Pos = self.Write_Hex('0gp')
            if Pos[:3] == '0PO':  #Position_Returned
                Integer = int('0x' + Pos[3:], 0)
            else:
                Code = int('0x' + Pos[3:], 0)  #Status returned
                return self.Convert_Status(Code)

        if Integer > 2147483647:  #Negative Number
            Integer = -self.Two_Compliment(Integer)
        Integer = 360. * float(Integer) / self.Counts_per_Rev
        return Integer

    def Rotate_To(self, Angle):
        """Rotate the stage to an absolute angle.

        If backlash correction is enabled the target is first overshot by 5
        degrees and then approached, so the final move is always in the same
        direction. The move is skipped if the stage is already within one
        encoder count of the target.

        Args:
            Angle (float): Target angle in degrees (taken modulo 360).

        Returns:
            float: Final stage angle, or a status string if the device
            returned a status code.
        """

        Angle = (Angle % 360)

        Current_Angle = self.Read_Position()
        if isinstance(Current_Angle, str) == True:  #Check is status returned
            return Current_Angle

        if abs(Current_Angle - Angle) >= 360. / self.Counts_per_Rev:  #Is it worth rotating?

            if self.Backlash_Correct == True:
                Initial_Angle = (Angle - 5)
            else:
                Initial_Angle = Angle

            Pulses = float(Initial_Angle) * self.Counts_per_Rev / 360.
            Pulses = int(np.round(Pulses))  #Closest to requested

            Pos = self.Write_Hex('0ma' + self.Number_to_Hex(Pulses))

            if self.Backlash_Correct == True:
                Pulses = float(Angle) * self.Counts_per_Rev / 360.
                Pulses = int(np.round(Pulses))  #Closest to requested

                Pos = self.Write_Hex('0ma' + self.Number_to_Hex(Pulses))

            if Pos[:3] == '0PO':  #Position_Returned
                Pos = int('0x' + Pos[3:], 0)
                return self.Read_Position(Pos)
            else:
                Code = int('0x' + Pos[3:], 0)  #Status returned
                return self.Convert_Status(Code)

        else:
            return Current_Angle

    def Rotate(self, Angle):
        """Rotate the stage by a relative angle.

        Args:
            Angle (float): Angle to rotate by, in degrees, added to the
                current position.

        Returns:
            float: Final stage angle, or a status string if the device
            returned a status code.
        """
        Current_Angle = self.Read_Position()
        if isinstance(Current_Angle, str) == True:  #Check is status returned
            return Current_Angle
        else:
            return self.Rotate_To(Current_Angle + Angle)
