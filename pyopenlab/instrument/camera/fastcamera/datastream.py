import os
import time
from typing import Callable, Generic, List, Tuple, TypeVar

from jisa.devices import Instrument
from jisa.devices.camera import Camera as JCamera
from jisa.devices.camera.frame import Frame
from jisa.devices.camera.frame import RGBFrame
from jisa.devices.camera.frame import U16RGBFrame
from jisa.devices.features import TemperatureControlled
import numpy as np
import pyjisa.autoload
from qtpy import uic
from qtpy.QtCore import Qt
from qtpy.QtCore import QThreadPool
from qtpy.QtCore import QTimer
from qtpy.QtCore import Signal
from qtpy.QtGui import QBrush
from qtpy.QtGui import QColor
from qtpy.QtGui import QIcon
from qtpy.QtGui import QImage
from qtpy.QtGui import QPainter
from qtpy.QtGui import QPen
from qtpy.QtGui import QPixmap
from qtpy.QtWidgets import *

import pyopenlab.datafile as df
from pyopenlab.instrument.camera.fastcamera.widgets import *

C = TypeVar("C", bound=JCamera)


class DataStreamGUI(QWidget, Generic[C]):

    def __init__(self, camera: C):

        super().__init__()

        self.camera = camera
        self.writer = None
        self.lastFrames = 0
        self.lastTime = 0
        self.wps = 0

        self.outputFile: QLineEdit
        self.h5ConversionOutput: QLineEdit
        self.mp4ConversionOutput: QLineEdit

        uic.loadUi((os.path.dirname(__file__) + '/dataStream.ui'), self)

    def enable(self):
        self.writer = self.camera.streamToFile(self.outputFile.text())

    def updateWPS(self):

        if self.writer is None:
            return

        frames = self.writer.getFrameCount()
        now = time.time()
        dFrame = frames - self.lastFrames
        dTime = now - self.lastTime
        self.wps = dFrame / dTime
        self.lastFrames = frames
        self.lastTime = now
