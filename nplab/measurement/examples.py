import builtins
from collections import deque
from typing import Deque
import pyjisa.autoload

import pyqtgraph as pg
import numpy     as np

from PyQt5.QtWidgets          import QApplication
from qtpy.QtGui               import QWindow
from qtpy.QtWidgets           import QVBoxLayout
from nplab.measurement.action import *
from h5py                     import Group, File

from nplab.measurement.gui                   import ActionQueueGUI, ActionSetupGUI
from nplab.measurement.actionqueue           import H5ActionQueue
from nplab.measurement.standard.images       import TakeImages
from nplab.measurement.standard.iv           import IVCurve
from nplab.measurement.standard.powersweep   import ChangePower, PowerSweep
from nplab.measurement.standard.repeat       import RepeatSweep
from nplab.measurement.standard.spectra      import TakeSpectra
from nplab.measurement.standard.voltagesweep import VoltageSweep
from nplab.measurement.sweep                 import H5Sweep

from jisa.devices.spectrometer import CameraSpectrometer, Kymera, Spectrometer, FakeSpectrometer
from jisa.devices.camera       import Andor3, Camera, FakeCamera
from jisa.devices.meter        import IMeter, TMeter
from jisa.devices.source       import VSource
from jisa.devices.smu          import K1234


from jisa.devices.spectrometer.feature import *

from pathlib import Path

from nplab.utils.gui_generator import GuiGenerator


# ===========================================================================================



app = QApplication([])

# Connect to instruments
zyla = FakeCamera()
spec = CameraSpectrometer(zyla)

smu  = K1234(None)

# Generate GUI, giving it our instruments and the actions/sweeps we want to be available for the queue
gui = GuiGenerator(
    instrument_dict    = {"spec": spec, "cam": zyla, "smu": smu.getSMU(0)}, 
    actions            = [TakeImages, TakeSpectra, IVCurve, ChangePower, RepeatSweep, VoltageSweep, PowerSweep], 
    dock_settings_path = str(Path.home().joinpath("settings.npy"))
)

gui.show()

app.exec()