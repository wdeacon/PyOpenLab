import builtins

import numpy as np
import pyjisa.autoload
from PyQt5.QtWidgets import QApplication
import pyqtgraph
from qtpy.QtGui import QWindow
from qtpy.QtWidgets import QVBoxLayout
from nplab.measurement.action import *
from h5py import Group, File

from nplab.measurement.gui import ActionQueueSetup, Setup
from nplab.measurement.queue import H5ActionQueue
from nplab.measurement.sweep import H5Sweep

from jisa.devices.spectrometer import Spectrometer, FakeSpectrometer
from jisa.devices.camera       import Camera, FakeCamera
from jisa.devices.meter        import IMeter, TMeter
from jisa.devices.source       import VSource
from jisa.devices.smu          import K1234


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

                img.attrs["Timestamp"]            = frame.getTimestamp()
                img.attrs["Integration Time [s]"] = self.camera.getIntegrationTime()


            self.sleep(self.delay)


    # =====[ On Finish ]============================================================================
    def finish(self, data: Group = None):
        pass


class IVCurve(H5Action):

    voltages = Parameter(name = "Voltages [V]", defaultValue = [0.0, 1.0, 2.0, 3.0], type = Type.AUTO)
    delay    = Parameter(name = "Delay Time",   defaultValue = 50,                   type = Type.TIME)
    autoOff  = Parameter(name = "Auto Off?",    defaultValue = True,                 type = Type.AUTO)

    vsource  = Instrument(name = "Voltage Source", type = VSource, required = True)
    imeter   = Instrument(name = "Ammeter",        type = IMeter,  required = True)
    tmeter   = Instrument(name = "Thermometer",    type = TMeter,  required = False)

    def __init__(self, description): 

        super().__init__("IV Curve", description)

        self.plot     = pyqtgraph.PlotWidget()
        self.plotData = self.plot.plotItem.plot([], [])


    def main(self, data: Group):

        self.plot.getPlotItem().clear()
            

        self.vsource.setVoltage(self.voltages[0])
        self.vsource.turnOn()
        self.imeter.turnOn()

        if self.tmeter is not None:
            self.tmeter.turnOn()

        sweep = np.zeros((len(self.voltages), 3))

        for (i, voltage) in enumerate(self.voltages):

            self.vsource.setVoltage(voltage)

            self.sleep(self.delay)

            sweep[i, 0] = voltage
            sweep[i, 1] = self.imeter.getCurrent()
            sweep[i, 2] = self.tmeter.getTemperature() if self.tmeter is not None else np.nan

            self.plotData.setData(sweep[:,0], sweep[:, 1])


        data.create_dataset("Sweep", data=sweep)


    def finish(self, data: Group):

        if self.autoOff:

            self.vsource.turnOff()
            self.imeter.turnOff()

            if self.tmeter is not None:
                self.tmeter.turnOff()


    def widget(self) -> pyqtgraph.PlotWidget:
        return self.plot


class RepeatSweep(H5Sweep[int]):

    repeats = Parameter(name = "Repeats", defaultValue = 5)

    def __init__(self, tag, actions = []):
        super().__init__("Repeat Sweep", tag, actions)

    def getValues(self):
        return list(range(self.repeats))

    def generate(self, value: int, actions: List[Action]) -> List[Action]:
        return actions
    
    def valueToString(self, value: int) -> str:
        return "%d" % value
    



class ChangeVoltage(SimpleAction):

    def __init__(self, vsource: VSource, voltage: float):
        super().__init__("Change Voltage (%.02g V)" % voltage, "V = %.02g V" % voltage)
        self.vsource = vsource
        self.voltage = voltage

    def main(self, data = None):
        self.vsource.setVoltage(self.voltage)
        self.vsource.turnOn()

    def finish(self, data = None):
        self.vsource.turnOff()
    
    


class VoltageSweep(H5Sweep[float]):

    voltages = Parameter(name = "Voltages [V]", defaultValue = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    off      = Parameter(name = "Off?",         defaultValue = True)

    source = Instrument(name = "Voltage Source", type = VSource, required = True)

    def __init__(self, tag, actions=[]):
        super().__init__("Voltage Sweep", tag, actions)

    def getValues(self):
        return self.voltages
    
    def generate(self, value: float, actions: List[Action]) -> List[Action]:
        return [ChangeVoltage(self.source, value)] + actions
    
    def valueToString(self, value: float):
        return "%.02g V" % value


# ===========================================================================================

app = QApplication([])

spec   = TakeSpectra("William")
iv     = IVCurve("Conductivity")
repeat = RepeatSweep("N", [spec, iv])
sweep  = VoltageSweep("V", [repeat])
k1234  = K1234(None)

spec.count        = 5
spec.delay        = 100
spec.spectrometer = FakeSpectrometer(None)
spec.camera       = FakeCamera(None)

iv.vsource = k1234.getSMU(0)
iv.imeter  = k1234.getSMU(0)

iv.voltages = list(np.arange(0, 60, 1))

repeat.repeats = 4

sweep.voltages = [0.0, 0.5, 1.0, 1.5, 2.0]
sweep.source   = k1234.getSMU(1)


queue = H5ActionQueue()
queue.addActions(spec, iv)

gui = ActionQueueSetup(queue, [TakeSpectra, IVCurve, RepeatSweep, VoltageSweep], [spec.spectrometer, spec.camera, k1234.getSMU(0)], File("test.h5", "w"))
gui.show()

app.exec()