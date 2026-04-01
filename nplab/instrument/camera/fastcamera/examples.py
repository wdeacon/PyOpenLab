import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3
from qtpy.QtWidgets import QApplication
from java.lang import System

from nplab.instrument.camera.fastcamera import FastCamera
from nplab.utils.gui_generator import GuiGenerator

try:

    app = QApplication([])

    camera     = FakeCamera(None)
    fastCamera = FastCamera(camera)

    lab = GuiGenerator({"camera": fastCamera})

    lab.show()
    app.exec()

except Exception as e:
    del app
    from jisa.gui import GUI
    GUI.showException(e)
finally:
    System.exit(0)