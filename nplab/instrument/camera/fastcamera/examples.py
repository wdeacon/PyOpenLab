import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3
from java.lang import System

from nplab.instrument.camera.fastcamera import FastCamera

camera     = FakeCamera()
fastCamera = FastCamera(camera)

fastCamera.show_gui(blocking=True)

System.exit(0)