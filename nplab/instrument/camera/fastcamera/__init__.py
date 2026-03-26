import sys

import pyjisa.autoload
import os
from threading import Thread
from typing import Callable, Generic, List, Tuple, TypeVar

from jpype.types import JInt, JDouble, JBoolean, JString
from java.lang import Double, Integer, Boolean, String

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import QByteArray, QThreadPool, Signal, Qt
from qtpy.QtGui import QImage, QPainter, QPixmap
from qtpy.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget
import qtpy.uic as uic
from nplab.instrument.camera import Camera

from jisa.devices.camera import Camera as JCamera, NPAdapter
from jisa.devices.camera.frame import Frame
from jisa.devices import Instrument

from nplab.utils.notified_property import NotifiedProperty

C = TypeVar("C", bound=JCamera)

class ImageListWidget(QWidget):
    def __init__(self, parent=None, thumbnail_size=120):
        super().__init__(parent)

        self._images = []
        self._thumbnail_size = thumbnail_size

        # Scroll area setup
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Container inside scroll area
        self.container = QWidget()
        self.layout = QHBoxLayout(self.container)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        self.layout.setAlignment(Qt.AlignLeft)

        # Stretch to keep items left-aligned
        self.layout.addStretch()

        self.scroll_area.setWidget(self.container)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.scroll_area)

    def _create_label(self, image: QImage) -> QLabel:
        """Create a QLabel for displaying a scaled image."""
        label = QLabel()

        pixmap = QPixmap.fromImage(image).scaled(
            self._thumbnail_size,
            self._thumbnail_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignCenter)
        return label

    def addImage(self, image: QImage):
        """Add a QImage to the widget."""
        if not isinstance(image, QImage):
            raise TypeError("Expected QImage")

        self._images.append(image)

        label = self._create_label(image)

        # Insert before the stretch (last item)
        self.layout.insertWidget(self.layout.count() - 1, label)

    def clearImages(self):
        """Remove all images from the widget."""
        self._images.clear()

        # Remove all widgets except the final stretch
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def getImages(self):
        """Return a copy of stored images."""
        return list(self._images)
    

class FastCameraGUI(QWidget, Generic[C]):

    captureCompleteSignal = Signal(list)

    def __init__(self, camera: C):

        super().__init__()

        self.cameraParameters : QFormLayout 
        self.numberOfFrames   : QSpinBox    
        self.captureButton    : QPushButton 
        self.liveViewButton   : QPushButton 
        self.cameraImage      : QLabel      
        self.capturedImages   : QGroupBox   
        self.clearImages      : QPushButton
        self.applyButton      : QPushButton
        
        uic.loadUi((os.path.dirname(__file__) + '/fcgui.ui'), self)

        self.camera   : C                 = camera
        self.captured : ImageListWidget   = ImageListWidget()
        self.pool     : QThreadPool       = QThreadPool()
        
        self._buffer = None

        self.capturedImages.layout().addWidget(self.captured)

        self.captureButton.clicked.connect(self.capture)
        self.liveViewButton.clicked.connect(self.live)
        self.clearImages.clicked.connect(self.clearAllImages)
        self.camera.addFrameListener(self.drawFrame)

        self.numberOfFrames.setValue(1)

        self._frames = []

        self.captureCompleteSignal.connect(self.captureComplete)
        self._params = []

        for param in camera.getAllParameters():

            w, g, s = self.createWidget(param.getDefaultValue(), param.getChoices())

            if w is None:
                continue

            w.setContentsMargins(0, 0, 0, 0)
            hbox = QHBoxLayout()
            hbox.addWidget(w, 1)
            setB = QPushButton("✓")
            setB.setFixedWidth(25)
            
            hbox.addWidget(setB,0)
            self.cameraParameters.addRow(param.getName(), hbox)

            s(param.getCurrentValue())

            self._params.append((w, g, s, param))

        self.applyButton.clicked.connect(self.applyParameters)
        

    def intTime(self):
        self.camera.setIntegrationTime(self.exposureTime.value())


    def capture(self):

        self.captureButton.setDisabled(True)

        def doCapture():
            frames = self.camera.getFrameSeries(self.numberOfFrames.value())
            self.captureCompleteSignal.emit(list(frames))

        self.pool.start(doCapture)


    def captureComplete(self, frames):

        self.captureButton.setDisabled(False)

        self._frames.clear()
        self._frames += frames

        self.captured.children().clear()

        for frame in frames:
            self.addFrame(frame)
        
        if not self.camera.isAcquiring():
            self.drawFrame(frames[len(frames) - 1])


    def clearAllImages(self):
        self.captured.clearImages()

    
    def live(self):

        if self.camera.isAcquiring():
            self.camera.stopAcquisition()
        else:
            self.camera.startAcquisition()


    def drawFrame(self, frame: Frame):

        if self._buffer is None or len(self._buffer) != self.camera.getFrameSize():

            self._buffer = frame.getARGBData()
            self._image  = QImage(self._buffer, frame.getWidth(), frame.getHeight(), QImage.Format.Format_ARGB32)
            self._pixmap = QPixmap(self._image)

            self.cameraImage.setPixmap(self._pixmap.scaled(self.cameraImage.width(), self.cameraImage.height(), Qt.KeepAspectRatio))

        else:
            frame.readARGBData(self._buffer)


    def addFrame(self, frame: Frame):
    
        image = QImage(frame.getARGBData(), frame.getWidth(), frame.getHeight(), QImage.Format.Format_ARGB32)
        self.captured.addImage(image)


    def applyParameters(self):

        for (w, g, s, p) in self._params:
            try:
                p.set(g())
            except Exception as e:
                print(e)

        for (w, g, s, p) in self._params:
            try:
                s(p.getCurrentValue())
            except Exception as e:
                print(e)


    def createWidget(self, defaultValue, choices = []) -> Tuple[QWidget, Callable, Callable]:

        if type(defaultValue) == Instrument.AutoQuantity:

            checkBox = QCheckBox("Auto")
            widget, getter, setter   = self.createWidget(defaultValue.getValue(), choices)

            if widget is None:
                return (None, None, None)

            widget.setDisabled(checkBox.isChecked())

            def updateCheckBox():
                widget.setDisabled(checkBox.isChecked())

            checkBox.stateChanged.connect(updateCheckBox)
            
            hbox = QHBoxLayout()
            cont = QWidget()
            cont.setLayout(hbox)

            hbox.addWidget(checkBox, 0)
            hbox.addWidget(widget, 1)

            def autoGetter():
                return Instrument.AutoQuantity(checkBox.isChecked(), getter())
            
            def autoSetter(aq: Instrument.AutoQuantity):
                checkBox.setChecked(aq.isAuto())
                setter(aq.getValue())

            return (cont, autoGetter, autoSetter)
        
        elif type(defaultValue) == Instrument.OptionalQuantity:

            checkBox               = QCheckBox("Enabled")
            widget, getter, setter = self.createWidget(defaultValue.getValue(), choices)

            if widget is None:
                return (None, None, None)

            widget.setDisabled(not checkBox.isChecked())

            def updateCheckBox():
                widget.setDisabled(not checkBox.isChecked())

            checkBox.stateChanged.connect(updateCheckBox)
            
            hbox = QHBoxLayout()
            cont = QWidget()
            cont.setLayout(hbox)

            hbox.addWidget(checkBox, 0)
            hbox.addWidget(widget, 1)

            def autoGetter():
                return Instrument.OptionalQuantity(checkBox.isChecked(), getter())
            
            def autoSetter(aq: Instrument.OptionalQuantity):
                checkBox.setChecked(aq.isUsed())
                setter(aq.getValue())

            return (cont, autoGetter, autoSetter)
        
        elif len(choices) > 0:

            choiceBox  = QComboBox()
            strChoices = [str(c) for c in choices]
            choiceBox.addItems(strChoices)

            def getter():
                return choices[choiceBox.currentIndex]
            
            def setter(value):
                choiceBox.setCurrentText(str(value))

            return (choiceBox, getter, setter)
        
        elif type(defaultValue) is Double:

            doubleBox = QDoubleSpinBox()
            doubleBox.setMinimum(-np.inf)
            doubleBox.setMaximum(+np.inf)

            return (doubleBox, doubleBox.value, doubleBox.setValue)

        elif type(defaultValue) is Integer:

            intBox = QSpinBox()
            intBox.setMinimum(-2147483647)
            intBox.setMaximum(2147483647)

            return (intBox, lambda: np.int32(intBox.value()), intBox.setValue)
        
        elif type(defaultValue) is Boolean:

            checkBox = QCheckBox()

            return (checkBox, checkBox.isChecked, checkBox.setChecked)
        
        elif type(defaultValue) is String:

            textBox = QLineEdit()

            return (textBox, textBox.text, textBox.setText)
        
        else:
            
            return (None, None, None)


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