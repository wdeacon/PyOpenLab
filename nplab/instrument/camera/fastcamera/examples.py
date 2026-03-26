import pyjisa.autoload

from jisa.devices.camera import FakeCamera, Andor2, Andor3

from nplab.instrument.camera.fastcamera import FastCamera

camera     = FakeCamera()
fastCamera = FastCamera(camera)

fastCamera.show_gui(blocking=True)