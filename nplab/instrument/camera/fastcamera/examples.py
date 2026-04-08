import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3
from jisa.devices.spectrometer import CameraSpectrometer, FakeSpectrometer
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

    app = QApplication([])

    camera     = FakeCamera(None)
    fastCamera = FastCamera(camera)
    spec       = CameraSpectrometer(camera, None)
    fastSpec   = FastSpectrometer(spec)
    

    lab = GuiGenerator({"spec": fastSpec})

    lab.show()

    app.exec()

except Exception as e:

    from jisa.gui import GUI
    GUI.showException(e)

finally:

    from java.lang import System # type: ignore
    System.exit(0)

