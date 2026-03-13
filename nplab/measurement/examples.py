import builtins

import pyjisa.autoload
from nplab.measurement import *
from h5py import Group, File

from nplab.measurement.sweep import H5Sweep

from jisa.devices.spectrometer import Spectrometer, FakeSpectrometer
from jisa.devices.camera import Camera, FakeCamera
from jisa.devices.camera.frame import Frame
from jisa.devices.meter import TMeter
from jisa.devices.source import VSource
from jisa.devices.smu import K1234


class TakeSpectra(H5Action):

    # =====[ Measurement Parameters ]================================================================ 
    count       = Parameter[int]   (name = "Number of Spectra",    defaultValue = 5)
    delay       = Parameter[int]   (name = "Delay Time [ms]",      defaultValue = 500,    type = Type.TIME)
    integration = Parameter[float] (name = "Integration Time [s]", defaultValue = 100e-3)

    # =====[ Instruments ]===========================================================================
    spectrometer = Instrument[Spectrometer] (name = "Spectrometer",      required = True)
    camera       = Instrument[Camera]       (name = "Microscope Camera", required = False)


    def __init__(self, description):
        super().__init__("Take Spectra", description)


    def main(self, data: Group):

        self.spectrometer.setIntegrationTime(self.integration)

        for i in range(self.count):

            self.message(type = MessageType.INFO, message = "Taking spectrum %d." % i)

            spectrum = self.spectrometer.getSpectrum()
            ds       = data.create_dataset(name = "Spectrum %d" % i, data = spectrum.listCounts())

            ds.attrs["Wavelengths [m]"]      = spectrum.listWavelengths()
            ds.attrs["Integration Time [s]"] = self.integration

            if self.camera is not None:

                self.message(type = MessageType.INFO, message = "Taking camera snapshot %d." % i)

                frame = self.camera.getFrame()
                img   = data.create_dataset(name = "Snapshot %d" % i, data = frame.getARGBImage())

                img.attrs["Timestamp"] = frame.getTimestamp()
                img.attrs["Integration Time [s]"] = self.camera.getIntegrationTime()


            self.sleep(self.delay)


    def finish(self, data: Group = None):
        pass



class RepeatSweep(H5Sweep[int]):

    repeats = Parameter[int](name = "Repeats", defaultValue = 5)

    def __init__(self, tag, actions = []):
        super().__init__("Repeat Sweep", tag, actions)

    def getValues(self):
        return list(range(self.repeats))

    def generate(self, value: int, actions: list) -> list:
        return actions
    
    def valueToString(self, value: int) -> str:
        return "%d" % value
    

class ChangeVoltage(SimpleAction):

    def __init__(self, vsource: VSource, voltage: float):
        super().__init__("Change Voltage", "V = %.02e V" % voltage)
        self.vsource = vsource
        self.voltage = voltage

    def main(self, data = None):
        self.vsource.setVoltage(self.voltage)
        self.vsource.turnOn()

    def finish(self, data = None):
        self.vsource.turnOff()
    
    
class VoltageSweep(H5Sweep[float]):

    voltages = Parameter[list](name = "Voltages [V]", defaultValue = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])

    source = Instrument[VSource](name = "Voltage Source", required = True)

    def __init__(self, tag, actions=[]):
        super().__init__("Voltage Sweep", tag, actions)

    def getValues(self):
        return self.voltages
    
    def generate(self, value: float, actions: list) -> list:
        return [ChangeVoltage(self.source, value)] + actions
    
    def valueToString(self, value: float):
        return "%.02g V" % value


# ===========================================================================================

spec   = TakeSpectra("Testing")
repeat = RepeatSweep("N", [spec])
sweep  = VoltageSweep("V", [repeat])

spec.count        = 5
spec.delay        = 100
spec.spectrometer = FakeSpectrometer(None)
spec.camera       = FakeCamera(None)

repeat.repeats = 4

sweep.voltages = [0.0, 0.5, 1.0, 1.5, 2.0]
sweep.source   = K1234(None).getSMU(0)

sweep.addMessageListener(lambda m: print("[%s] %s" % (m.pathString, m.message)))

print(["%s = %s" % (p.name, p.value) for p in spec.getParameters()])
print(["%s = %s" % (p.name, p.value) for p in spec.getInstruments()])

data   = File("/home/william/Desktop/test.h5", mode="w")
result = sweep.run(data)
data.close()