
from nplab.instrument.spectrometer import DummySpectrometer, Spectrometer
from nplab.measurement import *
from h5py import Group, File

from nplab.measurement.sweep import Sweep


class TakeSpectra(Action[Group]):

    # ==========[ Measurement Paramaters ]========== 
    numSpctra = Parameter[int](name = "Number of Spectra", defaultValue = 5)
    delayTime = Parameter[int](name = "Delay Time [ms]",   defaultValue = 500)

    # ===============[ Instruments ]================
    spectrometer = Instrument[Spectrometer](name = "Spectrometer", required = True)


    def __init__(self, description):
        super().__init__("Take Spectra", description)


    def main(self, data: Group = None):

        for i in range(self.numSpctra):

            self.message(type = MessageType.INFO, message = "Taking spectrum %d." % i)

            spectrum = self.spectrometer.read_spectrum()

            if data is not None:
                data.create_dataset(name = "Spectrum %d" % i, data = spectrum)

            self.sleep(self.delayTime)


    def finish(self, data: Group = None):
        pass



class RepeatSweep(Sweep[Group, int]):

    def __init__(self, tag, values, actions):
        super().__init__("Repeat Sweep", tag, values, actions)

    def generate(self, value: int, actions: list) -> list:
        return actions
    
    def valueToString(self, value: int) -> str:
        return "%d" % value
    
    def prepareData(self, tag: str, value: int, data: Group):
        return data.create_group("%s = %d" % (tag, value))
    
    def finish(self, data: Group = None):
        pass
    

spec              = TakeSpectra("Testing")
spec.numSpctra    = 12
spec.spectrometer = DummySpectrometer()
spec.delayTime    = 10

data  = File("/home/william/Desktop/test.h5", mode="w")
group = data.create_group("Spectra")

sweep = RepeatSweep("N", [0, 1, 2, 3, 4, 5], [spec])

sweep.addMessageListener(lambda msg: print("[%s] %s: %s" % (msg.pathString(), msg.type, msg.message)))

result = sweep.run(group)

print(result)