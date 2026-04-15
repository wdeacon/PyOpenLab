import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3, Lumenera
from jisa.devices.spectrometer import CameraSpectrometer, FakeSpectrometer, OceanOptics
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication

from nplab.instrument.camera.camera_with_location import CameraWithLocation
from nplab.instrument.camera.fastcamera import FastCamera
from nplab.instrument.spectrometer.fastspectrometer import FastSpectrometer
from nplab.instrument.spectrometer.fastspectrometer.csconfig import CSConfigGUI
from nplab.instrument.stage import DummyStage
from nplab.utils.gui_generator import GuiGenerator

try:

    app      = QApplication([])
    cam      = FakeCamera()
    spec     = CameraSpectrometer(cam, None)
    fastCam  = FastCamera(cam)
    cwl      = CameraWithLocation(fastCam, DummyStage())
    fastSpec = FastSpectrometer(spec)
    lab      = GuiGenerator({"cam": fastCam, "cwl": cwl}, dock_settings_path="/home/william/settings.npy")

    lab.show()
    app.exec()

except Exception as e:
    del app
    from jisa.gui import GUI
    GUI.showException(e)

