import sys

import pyjisa.autoload
import os
from threading import Thread
from typing import Callable, Generic, List, Tuple, TypeVar

import numpy as np
from nplab.instrument.camera import Camera

from jisa                      import Util
from jisa.devices.camera       import Camera as JCamera, NPAdapter
from jisa.devices.camera.frame import Frame, RGBFrame, U16RGBFrame

from nplab.instrument.camera.fastcamera.gui import FastCameraGUI, FastCameraPreviewGUI

from .widgets import *

from nplab.utils.notified_property import NotifiedProperty

from qtpy.QtCore import QThreadPool

C = TypeVar("C", bound=JCamera)

class FastCamera(Camera, Generic[C]):

    def __init__(self, camera: C):

        self._parameters = list(camera.getAllParameters())
        super().__init__()
        
        self.camera = NPAdapter(camera)
        self.buffer = None
        self.arr    = None
        self.pool   = QThreadPool()

        self.camera.getCamera().addFrameListener(self.updateFrame)


    def updateFrame(self, frame: Frame):

        try:

            height = frame.getHeight()
            width  = frame.getWidth()
            
            if self.buffer is None or self.rgb.shape[0] != height or self.rgb.shape[1] != width:
                self.buffer = frame.getARGBData()
                self.arr    = np.array(self.buffer)
                self.rgb    = np.empty((height, width, 3), dtype=np.uint8)
            else:
                frame.readARGBData(self.buffer)
                np.copyto(self.arr, self.buffer)

            argb2d = self.arr.view(np.uint8).reshape(height, width, 4)

            self.rgb[..., 0] = argb2d[..., 2]
            self.rgb[..., 1] = argb2d[..., 1]
            self.rgb[..., 2] = argb2d[..., 0]

            self.update_latest_frame(self.rgb)

        except Exception as e:
            print(e)

        finally:
            Util.sleep(10)


    def raw_snapshot(self):
        return True, np.array(self.camera.raw_snapshot())

    
    def get_next_frame(self, timeout=60, discard_frames=0, assert_live_view=True, raw=True) -> np.array:
        return np.array(self.camera.get_next_frame(timeout, discard_frames, assert_live_view, raw))
    

    @NotifiedProperty
    def live_view(self) -> bool:
        return self.camera.live_view()
    

    @live_view.setter
    def live_view(self, live: bool):
        self.camera.live_view(live)


    def exposure(self) -> float:
        return self.camera.getCamera().getIntegrationTime()


    def setExposure(self, time: float):
        self.camera.getCamera().setIntegrationTime(time)


    exposure = property(exposure, setExposure)

    def gain(self) -> float:
        return 0.0

    def setGain(self, gain: float):
        pass

    gain = property(gain, setGain)

    def getCamera(self) -> C:
        return self.camera.getCamera()
    

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
        return FastCameraGUI(self.camera.getCamera(), self)    

    def get_control_widget(self):
        return self.get_qt_ui()


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