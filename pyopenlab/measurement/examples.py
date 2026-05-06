import builtins
from collections import deque
from pathlib import Path
from typing import Deque

from h5py import File
from h5py import Group
from jisa.devices.camera import Andor2
from jisa.devices.camera import Andor3
from jisa.devices.camera import Camera
from jisa.devices.camera import FakeCamera
from jisa.devices.camera import Lumenera
from jisa.devices.camera import ThorCam
from jisa.devices.meter import IMeter
from jisa.devices.meter import TMeter
from jisa.devices.smu import K1234
from jisa.devices.source import VSource
from jisa.devices.spectrometer import CameraSpectrometer
from jisa.devices.spectrometer import FakeSpectrometer
from jisa.devices.spectrometer import Kymera
from jisa.devices.spectrometer import Spectrometer
from jisa.devices.spectrometer.feature import *
import numpy as np
import pyjisa.autoload
from PyQt5.QtWidgets import QApplication
import pyqtgraph as pg
from qtpy.QtGui import QWindow
from qtpy.QtWidgets import QVBoxLayout

from pyopenlab.instrument.camera.camera_with_location import CameraWithLocation
from pyopenlab.instrument.camera.fastcamera import FastCamera
from pyopenlab.instrument.stage.prior import ProScan
from pyopenlab.measurement.action import *
from pyopenlab.measurement.actionqueue import H5ActionQueue
from pyopenlab.measurement.gui import ActionQueueGUI
from pyopenlab.measurement.gui import ActionSetupGUI
from pyopenlab.measurement.standard.images import TakeImages
from pyopenlab.measurement.standard.iv import IVCurve
from pyopenlab.measurement.standard.powersweep import ChangePower
from pyopenlab.measurement.standard.powersweep import PowerSweep
from pyopenlab.measurement.standard.repeat import RepeatSweep
from pyopenlab.measurement.standard.spectra import TakeSpectra
from pyopenlab.measurement.standard.voltagesweep import VoltageSweep
from pyopenlab.measurement.sweep import H5Sweep
from pyopenlab.utils.gui_generator import GuiGenerator

# ===========================================================================================

app = QApplication([])

# Connect to instruments
newton = FakeCamera()

# Combine newton camera and kymera spectrograph into a spectrometer
spec = CameraSpectrometer(newton)

# # All instruments will have various .set...() methods to set configuration parmeters

# # Exposure time
# newton.setIntegrationTime(10e-6)

# # EMCCD Amplification
# newton.setAmplifierType(Andor2.AmplifierType.ELECTRON_MULTIPLYING)
# newton.setEMGain(100)

# # FVB and Isolated Crop
# newton.setImageMode(Camera.ImageMode.FULL_VERTICAL_BINNING)
# newton.setIsolatedCropHeight(100)
# newton.setIsolatedCropWidth(newton.getSensorWidth())
# newton.setIsolatedCropEnabled(True)

# Generate GUI, giving it our instruments and the actions/sweeps we want to be available for the queue
gui = GuiGenerator(instrument_dict={"spec": spec},
                   actions=[
                       TakeImages, TakeSpectra, IVCurve, ChangePower, RepeatSweep, VoltageSweep,
                       PowerSweep],
                   dock_settings_path=str(Path.home().joinpath("settings.npy")))

gui.show()

app.exec()
