import pyjisa.autoload
import numpy as np

from nplab.measurement.action import *
from h5py import Group

from jisa.devices.spectrometer import Spectrometer
from jisa.devices.camera import Camera

class TakeSpectra(H5Action):

    def __init__(self, description): 
        super().__init__("Take Spectra", description)

    # =====[ Measurement Parameters ]================================================================ 
    count       = Parameter(name = "Number of Spectra", defaultValue = 5,      range = (0, None))
    delay       = Parameter(name = "Delay Time",        defaultValue = 500,    type  = Type.TIME)
    integration = Parameter(name = "Integration Time",  defaultValue = 100e-3, type  = Type.SCIENTIFIC)

    # =====[ Instruments ]===========================================================================
    spectrometer = Instrument(name = "Spectrometer",      type = Spectrometer, required = True)
    camera       = Instrument(name = "Microscope Camera", type = Camera,       required = False)


    # =====[ Main Method ]===========================================================================
    def main(self, data: Group):

        self.spectrometer.setIntegrationTime(self.integration)

        spectra = data.create_group("Spectra")

        if self.camera is not None:
            snapshots = data.create_group("Snapshots")

        for i in range(self.count):

            self.message(type = MessageType.INFO, message = "Taking spectrum %d." % i)

            spectrum = self.spectrometer.getSpectrum()
            ds       = spectra.create_dataset(name = "Spectrum %d" % i, data = spectrum.listCounts())

            ds.attrs["Wavelengths [m]"]      = spectrum.listWavelengths()
            ds.attrs["Integration Time [s]"] = self.integration

            if self.camera is not None:

                self.message(type = MessageType.INFO, message = "Taking camera snapshot %d." % i)

                frame = self.camera.getFrame()
                img   = snapshots.create_dataset(
                    name = "Snapshot %d" % i, 
                    data = np.array(frame.getRGBBytes()).reshape(frame.getHeight(), frame.getWidth(), 3)
                )

                img.attrs["Timestamp"]            = frame.getTimestamp()
                img.attrs["Integration Time [s]"] = self.camera.getIntegrationTime()


            self.sleep(self.delay)


    # =====[ On Finish ]============================================================================
    def finish(self, data: Group = None):
        pass