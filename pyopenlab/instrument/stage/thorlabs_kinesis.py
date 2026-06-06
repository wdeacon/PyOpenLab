# -*- coding: utf-8 -*-
"""Python 3 wrappers for Thorlabs Kinesis motion controllers (.NET API via pythonnet).

Covers K-Cube and T-Cube DC servos and a benchtop piezo controller. It relies on
the Thorlabs Kinesis .NET API, accessed through the ``pythonnet`` (``clr``)
package, so the Kinesis DLLs must be importable. ``C:\\Program Files\\Thorlabs\\Kinesis``
is appended to ``sys.path`` at import time (a hack, but it works) so the
assemblies can be found.

Generalised from the trautsned/thorlabs_kenesis_python LTS300 example; so far
only tested on PRM1-Z8 actuators.
"""
import sys
import time

import clr

from pyopenlab.instrument.stage import Stage

clr.AddReference("System")
from System import Decimal  # System is part of the .NET framework, which clr provides

try:
    sys.path.append(r'C:\Program Files\Thorlabs\Kinesis')
    clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
    import Thorlabs.MotionControl.DeviceManagerCLI as DeviceManagerCLI
except Exception as e:
    print("Error importing the ThorLabs Kinesis .NET API.  It may not be in your PATH. "
          "Check you have installed the correct version (64/32 bit) of Kinesis, and that "
          "it is located in C:\\Program Files\\Thorlabs\\Kinesis.")

DeviceManagerCLI.DeviceManagerCLI.BuildDeviceList()
# list the serial numbers of the Kinesis-recognised devices connected
# devices = DeviceManagerCLI.DeviceManagerCLI.GetDeviceList()


def list_devices():
    """Rebuild the device list and return the connected Kinesis serial numbers."""
    DeviceManagerCLI.DeviceManagerCLI.BuildDeviceList()
    return DeviceManagerCLI.DeviceManagerCLI.GetDeviceList()


"""KCUBE"""
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")
import Thorlabs.MotionControl.KCube.DCServoCLI as KcubeDCServoCLI


class KCube(Stage):
    """K-Cube DC servo controller (single rotation/translation axis)."""

    axis_names = ('theta',)

    def __init__(self, serial_number):
        """Connect to the K-Cube, wait for settings to load and enable it.

        Args:
            serial_number: Kinesis serial number string of the K-Cube.
        """
        super(Stage, self).__init__()

        DeviceManagerCLI.DeviceManagerCLI.BuildDeviceList()
        self.device = KcubeDCServoCLI.KCubeDCServo.CreateKCubeDCServo(serial_number)
        self.device.Connect(serial_number)
        self.device.WaitForSettingsInitialized(5000)
        self.device.EnableDevice()

    def move(self, pos, axis=None, relative=False):
        """Move to an absolute position, blocking up to 60 s.

        Args:
            pos: Target position in device units.
            axis: Ignored (single axis).
            relative: Ignored; the move is always absolute.
        """
        self.device.MoveTo(Decimal(pos), 60000)

    def get_position(self, axis=None):
        """Return the current position as a float (in device units)."""
        return float(self.device.Position.ToString())


"""TCUBE"""
clr.AddReference("Thorlabs.MotionControl.TCube.DCServoCLI")
import Thorlabs.MotionControl.TCube.DCServoCLI as TcubeDCServoCLI


class TCube(Stage):
    """T-Cube DC servo controller (single rotation/translation axis)."""

    axis_names = ('theta',)

    def __init__(self, serial_number):
        """Connect to the T-Cube, wait for settings to load and enable it.

        Args:
            serial_number: Kinesis serial number string of the T-Cube.
        """
        super(Stage, self).__init__()

        DeviceManagerCLI.DeviceManagerCLI.BuildDeviceList()
        self.device = TcubeDCServoCLI.TCubeDCServo.CreateTCubeDCServo(serial_number)
        self.device.Connect(serial_number)
        self.device.WaitForSettingsInitialized(5000)
        self.device.EnableDevice()

    def move(self, pos, axis=None, relative=False):
        """Move to an absolute position, blocking up to 60 s.

        Args:
            pos: Target position in device units.
            axis: Ignored (single axis).
            relative: Ignored; the move is always absolute.
        """
        self.device.MoveTo(Decimal(pos), 60000)

    def get_position(self, axis=None):
        """Return the current position as a float (in device units)."""
        return float(self.device.Position.ToString())


"""Benchtop Piezo

Currently tested with BCP203 (may not be correct)
"""
clr.AddReference("Thorlabs.MotionControl.Benchtop.PiezoCLI")
import Thorlabs.MotionControl.Benchtop.PiezoCLI as BenchtopPiezoCLI


class BenchtopPiezo(Stage):
    """Multi-channel Thorlabs benchtop piezo controller (tested with BPC203).

    Each Kinesis channel becomes an axis named ``channel_<i>``; positions here
    are output voltages rather than displacements.
    """

    axis_names = None
    connected = False
    channels = []
    device = None

    def __init__(self, serial_number):
        """Connect to the benchtop piezo and initialise its channels.

        Args:
            serial_number: Kinesis serial number string of the controller.
        """
        self._serial_number = serial_number
        DeviceManagerCLI.DeviceManagerCLI.BuildDeviceList()
        self.device = BenchtopPiezoCLI.BenchtopPiezo.CreateBenchtopPiezo(serial_number)
        self.connect()
        super(Stage, self).__init__()

    def connect(self):
        """Initialise communications, populate channel list, etc."""
        self.device.Connect(self._serial_number)
        self.connected = True
        assert len(self.channels) == 0, "Error connecting: we've already initialised channels!"
        for i in range(self.device.ChannelCount):
            chan = self.device.GetChannel(i + 1)  # Kinesis channels are one-indexed
            chan.WaitForSettingsInitialized(5000)
            chan.StartPolling(250)  # getting the voltage only works if you poll!
            time.sleep(0.5)  # ThorLabs have this in their example...
            chan.EnableDevice()
            # I don't know if the lines below are necessary or not - but removing them
            # may or may not work...
            time.sleep(0.5)
            config = chan.GetPiezoConfiguration(chan.DeviceID)
            info = chan.GetDeviceInfo()
            max_v = Decimal.ToDouble(chan.GetMaxOutputVoltage())
            self.channels.append(chan)
        self.axis_names = tuple("channel_{}".format(i) for i in range(self.device.ChannelCount))

    def close(self):
        """Shut down communications"""
        if not self.connected:
            print(f"Not closing piezo device {self._serial_number}, it's not open!")
            return
        for chan in self.channels:
            chan.StopPolling()
        self.channels = []
        self.device.Disconnect(True)

    def __del__(self):
        try:
            if self.connected:
                self.close()
        except:
            print(f"Error closing communications on deletion of device {self._serial_number}")

    def set_output_voltages(self, voltages):
        """Set the output voltage"""
        assert len(voltages) == len(
            self.channels), "You must specify exactly one voltage per channel"
        for chan, v in zip(self.channels, voltages):
            chan.SetOutputVoltage(Decimal(v))

    def get_output_voltages(self):
        """Retrieve the output voltages as a list of floating-point numbers"""
        return [Decimal.ToDouble(chan.GetOutputVoltage()) for chan in self.channels]

    output_voltages = property(get_output_voltages, set_output_voltages)

    def move(self, pos, axis=None, relative=False):
        """Move the piezo stage.  For now, this is done in volts."""
        if axis is None:
            for p, ax in zip(pos, self.axis_names):
                self.move_axis(p, ax, relative=relative)
        else:
            self.move_axis(pos, axis, relative=relative)

    def move_axis(self, pos, axis, relative=False):
        """Move one axis (currently in volts)"""
        chan = self.select_axis(self.channels, axis)
        if relative:
            # emulate relative moves
            pos += Decimal.ToDouble(chan.GetOutputVoltage())
        chan.SetOutputVoltage(Decimal(pos))

    def get_position(self, axis=None):
        """Return the output voltage of one axis, or a list for all axes.

        Args:
            axis: Axis name; if None, return a list of voltages for every axis.

        Returns:
            The output voltage (float), or a list of voltages when axis is None.
        """
        if axis is None:
            return [self.get_position(ax) for ax in self.axis_names]
        else:
            chan = self.select_axis(self.channels, axis)
            return Decimal.ToDouble(chan.GetOutputVoltage())
