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
from nplab.measurement.standard.images import TakeImages
from nplab.measurement.standard.iv import IVCurve
from nplab.measurement.standard.repeat import RepeatSweep
from nplab.measurement.standard.spectra import TakeSpectra
from nplab.measurement.standard.voltagesweep import VoltageSweep
from nplab.measurement.sweep import H5Sweep

from jisa.devices.spectrometer import CameraSpectrometer, Kymera, Spectrometer, FakeSpectrometer
from jisa.devices.camera       import Andor3, Camera, FakeCamera
from jisa.devices.meter        import IMeter, TMeter
from jisa.devices.source       import VSource
from jisa.devices.smu          import K1234

from pathlib import Path

from nplab.utils.gui_generator import GuiGenerator


# ===========================================================================================

app = QApplication([])

camera = FakeCamera()
spec   = CameraSpectrometer(camera)
smu    = K1234(None)

gui = GuiGenerator(
    instrument_dict    = {"spec": spec, "cam": camera, "smu": smu.getSMU(0)}, 
    actions            = [TakeImages, TakeSpectra, IVCurve, RepeatSweep, VoltageSweep], 
    dock_settings_path = str(Path.home().joinpath("settings.npy"))
)

gui.show()

app.exec()