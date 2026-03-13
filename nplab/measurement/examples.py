from nplab.instrument.spectrometer import DummySpectrometer, Spectrometer
from nplab.measurement import *
from h5py import Group, File


class TakeSpectra(Action[Group]):

    numSpctra    = Parameter[int](name = "Number of Spectra", defaultValue = 5)
    delayTime    = Parameter[int](name = "Delay Time [ms]",   defaultValue = 500)

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


spec              = TakeSpectra("Testing")
spec.numSpctra    = 12
spec.spectrometer = DummySpectrometer()

spec._messageListeners.append(lambda type, message: print("%s: %s" % (type, message)))

data  = File("/home/william/Desktop/test.h5", mode="w")
group = data.create_group("Spectra")

spec.run(data = group)

print(group)