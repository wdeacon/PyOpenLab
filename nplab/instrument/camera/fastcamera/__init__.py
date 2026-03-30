import sys

import pyjisa.autoload
import os
from threading import Thread
from typing import Callable, Generic, List, Tuple, TypeVar

import numpy as np
from nplab.instrument.camera import Camera

from jisa.devices.camera import Camera as JCamera, NPAdapter

from nplab.instrument.camera.fastcamera.gui import FastCameraGUI

from .widgets import *

from nplab.utils.notified_property import NotifiedProperty

C = TypeVar("C", bound=JCamera)

class FastCamera(Camera, Generic[C]):

    def __init__(self, camera: C):

        self._parameters = list(camera.getAllParameters())
        super().__init__()
        self._camera     = NPAdapter(camera)
        camera.addFrameListener(self.updateFrame)

    def updateFrame(self, frame):
        self.update_latest_frame(np.array(frame.image()))

    def raw_snapshot(self):
        return True, np.array(self._camera.raw_snapshot())

    
    def get_next_frame(self, timeout=60, discard_frames=0, assert_live_view=True, raw=True) -> np.array:
        return np.array(self._camera.get_next_frame(timeout, discard_frames, assert_live_view, raw))
    

    @NotifiedProperty
    def live_view(self) -> bool:
        return self._camera.live_view()
    
    @live_view.setter
    def live_view(self, live: bool):
        self._camera.live_view(live)


    def getCamera(self) -> C:
        return self._camera.getCamera()
    
    def camera_parameter_names(self):
        return [p.getName() for p in self._parameters]
    
    def get_camera_parameter(self, parameter_name):
        found = [p for p in self._parameters if p.getName() == parameter_name]
        print(found)
        return found[0].getCurrentValue()
    
    def set_camera_parameter(self, parameter_name, value):
        found = [p for p in self._parameters if p.getName() == parameter_name]
        return found[0].set(value)

    def get_qt_ui(self, control_only=False, parameters_only=False):
        return FastCameraGUI(self._camera.getCamera())


class FastCameraBad(Camera, Generic[C]):

    def __init__(self, camera: C):

        self._parameters = list(camera.getAllParameters())
        super().__init__()
        self._camera     = NPAdapter(camera)

    def raw_snapshot(self):
        return True, np.array(self._camera.raw_snapshot())

    def getCamera(self) -> C:
        return self._camera.getCamera()
    
    def camera_parameter_names(self):
        return [p.getName() for p in self._parameters]
    
    def get_camera_parameter(self, parameter_name):
        found = [p for p in self._parameters if p.getName() == parameter_name]
        print(found)
        return found[0].getCurrentValue()
    
    def set_camera_parameter(self, parameter_name, value):
        found = [p for p in self._parameters if p.getName() == parameter_name]
        return found[0].set(value)

    # def get_qt_ui(self, control_only=False, parameters_only=False):
    #     return FastCameraGUI(self._camera)