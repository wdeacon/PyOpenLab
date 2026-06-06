"""Serial driver for a rotation stage and a filter-wheel power-calibration helper."""
import os
import struct
import time

import numpy as np

from pyopenlab.instrument import serial_instrument as serial


class Rotation_Stage_Backend(serial.SerialInstrument):
    """Low-level serial interface to a rotation stage using ASCII-hex commands.

    The device addresses positions as 18-bit counts over a full revolution
    (262144 counts = 360 degrees).
    """

    def __init__(self, port=None):
        super(Rotation_Stage_Backend, self).__init__()

    def Number_to_Hex(self, Input, Min_Size=8):
        """Encode an integer as a left-zero-padded list of hex-digit bytes.

        Args:
            Input: Non-negative integer to encode.
            Min_Size: Minimum number of digits; the result is left-padded with
                ``'0'`` digits to reach this length.

        Returns:
            A list of single-character ``bytes`` objects, one per hex digit.
        """
        Hex = hex(Input)[2:]
        Output = []
        for i in Hex:
            Output.append(i)
        while len(Output) < Min_Size:
            Output = ['0'] + Output
        Output = list(map(str.encode, Output))
        return Output

    def Convert_Status(self, Code):
        """Map a numeric status code to its human-readable message.

        Args:
            Code: Status code returned by the device.

        Returns:
            The matching status string, or ``'Reserved Response Code'`` for
            codes of 14 or above.
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

    def Get_Status(self):
        """Query the device status.

        Returns:
            The decoded status string for the device's current state.
        """
        Packer = struct.Struct(format=b'ccc')
        Message = Packer.pack(*[b'0', b'g', b's'])
        self.Port.write(Message)
        Response = self.Port.readline()

        Code = int(b'0x' + Response[3:], 0)

        return self.Convert_Status(Code)

    def Rotate(self, Angle):
        """Rotate relative to the current position by ``Angle`` degrees.

        Args:
            Angle: Relative rotation in degrees; normalised into ``[0, 360)``
                before being sent.

        Returns:
            A ``'Position: <degrees>'`` string if the device reports a position,
            otherwise the decoded status string.
        """
        Message = [b'0', b'm', b'r']

        while Angle < 0:
            Angle += 360.
        Angle = Angle % 360

        Angle = 262144. * Angle / 360

        Angle = int(Angle)
        Angle = self.Number_to_Hex(Angle)

        Message += Angle
        Packer = struct.Struct(format=b'ccccccccccc')
        Message = Packer.pack(*Message)

        self.Port.write(Message)
        Response = self.Port.readline()

        Code = int(b'0x' + Response[3:], 0)

        if Response[:3] == b'0PO':
            Position = float(Code) / 262144
            return 'Position: ' + str(Position * 360)
        else:
            return self.Convert_Status(Code)

    def Rotate_To(self, Angle):
        """Rotate to an absolute position of ``Angle`` degrees.

        Args:
            Angle: Absolute target in degrees; normalised into ``[0, 360)``
                before being sent.

        Returns:
            A ``'Position: <degrees>'`` string if the device reports a position,
            otherwise the decoded status string.
        """
        Message = [b'0', b'm', b'a']

        while Angle < 0:
            Angle += 360.
        Angle = Angle % 360

        Angle = (262144. * Angle) / 360

        Angle = int(Angle)
        Angle = self.Number_to_Hex(Angle)

        Message += Angle
        Packer = struct.Struct(format=b'ccccccccccc')
        Message = Packer.pack(*Message)

        self.Port.write(Message)
        Response = self.Port.readline()

        Code = int(b'0x' + Response[3:], 0)

        if Response[:3] == b'0PO':
            Position = float(Code) / 262144
            return 'Position: ' + str(Position * 360)
        else:
            return self.Convert_Status(Code)

    def Get_Position(self):
        """Query the current absolute position.

        Returns:
            A ``'Position: <degrees>'`` string if the device reports a position,
            otherwise the decoded status string.

        Note:
            Returns a formatted string rather than a numeric angle, and the
            response parsing is known to fail for small angles. Logged, not
            fixed.
        """
        Packer = struct.Struct(format=b'ccc')
        Message = Packer.pack(*[b'0', b'g', b'p'])

        self.Port.write(Message)
        Response = self.Port.readline()
        Code = int(b'0x' + Response[3:], 0)

        if Response[:3] == b'0PO':
            Position = float(Code) / 262144
            return 'Position: ' + str(Position * 360)
        else:
            return self.Convert_Status(Code)


class Filter_Wheel(object):
    """Rotation-stage filter wheel calibrated to set optical power via a curve.

    The wheel maps a rotation angle to a transmitted power using a stored
    power curve, allowing a target power to be requested directly.

    Args:
        Port: Serial port the rotation stage is connected to.
        Power_Meter: Optional power meter object exposing a ``read`` attribute,
            used when generating a power curve.
        Power_Curve_Directory: Directory prefix for loading/saving the power
            curve ``.npy`` file.

    Note:
        ``Power_Curve_Directory`` defaults to the ``os.path`` module, and the
        constructor immediately does ``Power_Curve_Directory + '...npy'``, which
        raises ``TypeError`` unless a string path is supplied. Logged, not
        fixed.
    """

    def __init__(self, Port='COM20', Power_Meter=None, Power_Curve_Directory=os.path):
        self.Stage = Rotation_Stage_Backend(Port)
        self.Power_Curve = np.load(Power_Curve_Directory + 'Filter_Wheel_Power_Curve.npy')
        self.Power_Curve_Directory = Power_Curve_Directory
        self.Power_Meter = Power_Meter
        self.Angle_Range = [0, 360]  #230

    def Return_Home(self):
        """Rotate the wheel to its home angle (180 degrees)."""
        self.Stage.Rotate_To(180)  #100

    def Generate_Power_Curve(self, Number_of_Points=30, Measurements_per_Point=10, Background=0.):
        """Sweep the wheel and record a power curve at evenly spaced angles.

        Steps the wheel across ``Angle_Range`` and stores the measured powers in
        ``self.Power_Curve`` as ``[angles, powers_in_mW]``.

        Args:
            Number_of_Points: Number of angles sampled across the range.
            Measurements_per_Point: Power readings averaged at each angle.
            Background: Background power subtracted before scaling to mW.
        """
        if self.Power_Meter is None:
            print('No Power Meter Defined!')
            return

        Input_Angles = np.linspace(self.Angle_Range[0], self.Angle_Range[1], Number_of_Points)

        Output_Angles = []
        Output_Powers = []

        self.Stage.Rotate_To(self.Angle_Range[0])
        time.sleep(2)

        for i in Input_Angles:
            Pos = self.Stage.Rotate_To(i)
            time.sleep(0.5)
            Pos = float(Pos[9:])
            #            if Pos>295:
            #                Pos-=360
            Output_Angles.append(Pos)
            Power = []
            while len(Power) < Measurements_per_Point:
                Power.append(self.Power_Meter.read)
            Output_Powers.append(np.mean(Power))
            time.sleep(0.5)
            print('Current Angle: ' + str(round(Pos, 2)))

        self.Stage.Rotate_To(self.Angle_Range[0])  #-190

        self.Power_Curve = np.array([Output_Angles, 1000. * (np.array(Output_Powers) - Background)])

    def Generate_Power_Curve_v2(self,
                                Number_of_Points=30,
                                Measurements_per_Point=10,
                                Background=0.):
        """Build a power curve adaptively, sampling where power changes fastest.

        Starts from the range endpoints and repeatedly inserts a new sample
        midway across the largest adjacent power gap until ``Number_of_Points``
        points have been collected. Stores ``[angles, powers_in_mW]`` in
        ``self.Power_Curve``.

        Args:
            Number_of_Points: Total number of samples to collect.
            Measurements_per_Point: Power readings (median-combined) per angle.
            Background: Background power subtracted before scaling to mW.

        Raises:
            Exception: If no power meter is configured.
        """
        if self.Power_Meter is None:
            print('No Power Meter Defined!')
            raise Exception('Lacking Power Meter')

        def Measure():
            Power = []

            while len(Power) < Measurements_per_Point:
                try:
                    Power.append(self.Power_Meter.read)
                except:
                    Dump = 1
            return np.median(Power)

        def Rotate_Catch(Angle):
            Pos = None
            while Pos is None:
                try:
                    Pos = self.Stage.Rotate_To(Angle)
                    time.sleep(0.5)
                    Pos = float(Pos[9:])
                except:
                    Pos = None
            return Pos % 360

        Angles = []
        Powers = []
        for i in [self.Angle_Range[0], self.Angle_Range[1]]:
            Pos = Rotate_Catch(i)
            Angles.append(Pos)
            Powers.append(Measure())

        while len(Powers) < Number_of_Points:
            Diff = []
            n = 1
            while n < len(Powers):
                Diff.append(Powers[n - 1] - Powers[n])
                n += 1
            print('Points:' + str(len(Powers)) + '. Average Power Seperation: ' +
                  str(round(np.mean(Diff) * 1000000, 2)) + 'uW')
            Next = np.argmax(Diff)
            #print Next
            Next_Angle = 0.5 * (Angles[Next] + Angles[Next + 1])
            Pos = Rotate_Catch(Next_Angle)
            Angles = Angles[:Next + 1] + [Pos] + Angles[Next + 1:]
            Powers = Powers[:Next + 1] + [Measure()] + Powers[Next + 1:]

        self.Return_Home()
        self.Power_Curve = np.array([Angles, 1000. * (np.array(Powers) - Background)])

    def Save_Power_Curve(self):
        """Save the current power curve to ``Power_Curve_Directory`` as ``.npy``."""
        np.save(self.Power_Curve_Directory + 'Filter_Wheel_Power_Curve.npy', self.Power_Curve)

    def Set_To_Power(self, Power):
        """Rotate the wheel to deliver the requested power.

        Linearly interpolates the stored power curve to find the angle for
        ``Power`` and rotates there.

        Args:
            Power: Desired output power, in the units of the stored curve.

        Returns:
            The angle rotated to, or ``None`` if ``Power`` is outside the
            curve's available range (a message is printed in that case).
        """
        if Power > np.max(self.Power_Curve[1]) or Power < np.min(self.Power_Curve[1]):
            print('Outside available power limits!')
            print('Please enter a value between ' + str(np.min(self.Power_Curve[1])) + ' and ' +
                  str(np.max(self.Power_Curve[1])))
            return

        Lower_Angle = 0
        while self.Power_Curve[1][Lower_Angle] >= Power:
            Lower_Angle += 1
        Lower_Angle -= 1

        if Lower_Angle == len(self.Power_Curve[1]):
            Lower_Angle -= 1

        Angles = [self.Power_Curve[0][Lower_Angle], self.Power_Curve[0][Lower_Angle + 1]]
        Powers = [self.Power_Curve[1][Lower_Angle], self.Power_Curve[1][Lower_Angle + 1]]

        m = (Angles[1] - Angles[0]) / (Powers[1] - Powers[0])
        c = Angles[0] - (m * Powers[0])

        Angle = (m * Power) + c

        print('Rotating To: ' + str(round(Angle, 2)))

        self.Stage.Rotate_To(Angle)

        return Angle
