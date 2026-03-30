import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3
from qtpy.QtWidgets import QApplication
from java.lang import System

from nplab.instrument.camera.fastcamera import FastCamera
from nplab.utils.gui_generator import GuiGenerator

app = QApplication([])

camera     = FakeCamera()
fastCamera = FastCamera(camera)

lab = GuiGenerator({"camera": fastCamera})

lab.show()
app.exec()