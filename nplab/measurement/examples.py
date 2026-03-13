import builtins

import pyjisa.autoload
from nplab.measurement import *
from h5py import Group, File

from nplab.measurement.sweep import H5Sweep

from jisa.devices.spectrometer import Spectrometer, FakeSpectrometer
from jisa.devices.meter import TMeter
from jisa.devices.source import VSource
from jisa.devices.smu import K1234


class TakeSpectra(H5Action):

    # ==========[ Measurement Paramaters ]========== 
    numSpctra = Parameter[int](name = "Number of Spectra", defaultValue = 5)
    delayTime = Parameter[int](name = "Delay Time [ms]", defaultValue = 500, type = Type.TIME)

    # ===============[ Instruments ]================
    spectrometer = Instrument[Spectrometer](name = "Spectrometer", required = True)
    thermometer  = Instrument[TMeter](name = "Thermometer", required = False)


    def __init__(self, description):
        super().__init__("Take Spectra", description)


    def main(self, data: Group = None):

        for i in range(self.numSpctra):

            self.message(type = MessageType.INFO, message = "Taking spectrum %d." % i)

            spectrum = self.spectrometer.getSpectrum()

            if data is not None:
                ds = data.create_dataset(name = "Spectrum %d" % i, data = spectrum.listCounts())
                ds.attrs["Wavelengths [m]"] = spectrum.listWavelengths()

                if (self.thermometer is not None):
                    ds.attrs["Temperature [K]"] = self.thermometer.getTemperature()

            self.sleep(self.delayTime)


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
    source   = Instrument[VSource](name = "Voltage Source", required = True)

    def __init__(self, tag, actions=[]):
        super().__init__("Voltage Sweep", tag, actions)

    def getValues(self):
        return self.voltages
    
    def generate(self, value: float, actions: list) -> list:
        return [ChangeVoltage(self.source, value)] + actions
    
    def valueToString(self, value: float):
        return "%.02g V" % value


spec              = TakeSpectra("Testing")
spec.numSpctra    = 1
spec.spectrometer = FakeSpectrometer(None)
spec.delayTime    = 10

data  = File("/home/william/Desktop/test.h5", mode="w")

repeat = RepeatSweep("N", [spec])
repeat.repeats = 4

sweep = VoltageSweep("V", [repeat])
sweep.source = K1234(None).getSMU(0)

sweep.addMessageListener(lambda m: print("[%s] %s" % (m.pathString, m.message)))

result = sweep.run(data)

data.close()

print(result.type)