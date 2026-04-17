import builtins

import numpy as np
import pyjisa.autoload
from PyQt5.QtWidgets import QApplication
import pyqtgraph
from qtpy.QtGui import QWindow
from qtpy.QtWidgets import QVBoxLayout
from nplab.measurement.action import *
from h5py import Group, File

from nplab.measurement.gui import ActionQueueGUI, ActionSetupGUI
from nplab.measurement.actionqueue import H5ActionQueue
from nplab.measurement.standard.iv import IVCurve
from nplab.measurement.standard.repeat import RepeatSweep
from nplab.measurement.standard.spectra import TakeSpectra
from nplab.measurement.standard.voltagesweep import VoltageSweep
from nplab.measurement.sweep import H5Sweep

from jisa.devices.spectrometer import Spectrometer, FakeSpectrometer
from jisa.devices.camera       import Camera, FakeCamera
from jisa.devices.meter        import IMeter, TMeter
from jisa.devices.source       import VSource
from jisa.devices.smu          import K1234

from nplab.utils.gui_generator import GuiGenerator


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

gui = GuiGenerator(
    instrument_dict    = {"spec": spec.spectrometer, "cam": spec.camera, "smu": k1234.getSMU(0)}, 
    actions            = [TakeSpectra, IVCurve, RepeatSweep, VoltageSweep], 
    dock_settings_path = "/home/william/settings.npy"
)

gui.show()

app.exec()