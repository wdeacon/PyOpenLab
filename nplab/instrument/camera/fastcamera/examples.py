import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication

from nplab.instrument.camera.fastcamera import FastCamera
from nplab.utils.gui_generator import GuiGenerator

try:

    app = QApplication([])

    camera     = FakeCamera(None)
    fastCamera = FastCamera(camera)

#    fastCamera.show_gui(blocking=True)

    lab = GuiGenerator({"camera": fastCamera})

    lab.show()
    app.exec()

except Exception as e:

    from jisa.gui import GUI
    GUI.showException(e)

finally:

    from java.lang import System # type: ignore
    System.exit(0)

