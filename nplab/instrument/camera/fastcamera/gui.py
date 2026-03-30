import h5py
import pyjisa.autoload
import os
import numpy as np

from typing import Callable, Generic, List, Tuple, TypeVar

from jisa.devices              import Instrument
from jisa.devices.camera       import Camera as JCamera
from jisa.devices.camera.frame import Frame, FrameThread, RGBFrame, U16RGBFrame
from jisa.devices.features     import TemperatureControlled

from qtpy import uic
from qtpy.QtCore import QTimer, Qt, QThreadPool, Signal
from qtpy.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap
from qtpy.QtWidgets import *

from nplab.instrument.camera.fastcamera.datastream import DataStreamGUI
from nplab.instrument.camera.fastcamera.widgets import *

import nplab.datafile as df


C = TypeVar("C", bound=JCamera)

class FastCameraGUI(QWidget, Generic[C]):

    captureCompleteSignal = Signal(list)
    clearImagesSignal     = Signal()
    mp4Signal             = Signal()
    h5Signal              = Signal()
    warningIcon           = QIcon.fromTheme("dialog-warning")

    def __init__(self, camera: C):

        super().__init__()
        
        self.camera              = camera
        self.captured            = ImageListWidget()
        self.streamer            = DataStreamGUI(camera)
        self.pool                = QThreadPool()
        self.buffer              = None
        self.frames: List[Frame] = []
        self.params              = []
        self.errorMessage        = QErrorMessage()
        self.stream: FrameThread = None

        # Define types for automatically linked widgets
        self.cameraParameters    : QFormLayout 
        self.numberOfFrames      : QSpinBox    
        self.captureButton       : QPushButton 
        self.liveViewButton      : QPushButton 
        self.cameraImage         : QLabel      
        self.capturedImages      : QGroupBox   
        self.clearImages         : QPushButton
        self.applyButton         : QPushButton
        self.refreshButton       : QPushButton
        self.temperatureControl  : QGroupBox
        self.streamBox           : QGroupBox
        self.currentTemperature  : QLCDNumber
        self.crosshairButton     : QPushButton
        self.crosshairPixels     : QSpinBox
        self.writeImages         : QPushButton
        self.saveImages          : QPushButton
        self.streamToDiskButton  : QPushButton
        self.streamFile          : QLineEdit
        self.streamBrowse        : QPushButton
        self.mp4Button           : QPushButton
        self.h5Button            : QPushButton
        self.writingMP4          : QLabel
        self.writingH5           : QLabel
         
        # Load UI from file
        uic.loadUi((os.path.dirname(__file__) + '/fcgui.ui'), self)

        # Check if the camera implements some sort of temperature control
        if isinstance(camera, TemperatureControlled):
            self.timer = QTimer()
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self.updateTemperature)
            self.timer.start()
            self.temperatureControl.setDisabled(False)
        else:
            self.temperatureControl.setDisabled(True)
            


        self.capturedImages.layout().addWidget(self.captured)


        def reEnable():

            if self.writingMP4.isVisible() or self.writingH5.isVisible():
                pass
            else:
                self.streamFile.setDisabled(False)
                self.streamBrowse.setDisabled(False)
                self.streamToDiskButton.setChecked(False)
                self.streamToDiskButton.setDisabled(False)
                self.mp4Button.setDisabled(False)
                self.h5Button.setDisabled(False)


        def doneMP4():
            self.writingMP4.setVisible(False)
            reEnable()


        def doneH5():
            self.writingH5.setVisible(False)
            reEnable()

        # Connect QT signals
        self.captureButton.clicked.connect(self.capture)
        self.liveViewButton.clicked.connect(self.live)
        self.clearImages.clicked.connect(self.clearAllImages)
        self.captureCompleteSignal.connect(self.captureComplete)
        self.applyButton.clicked.connect(self.applyParameters)
        self.refreshButton.clicked.connect(self.refreshParameters)
        self.writeImages.clicked.connect(self.saveToH5)
        self.saveImages.clicked.connect(self.savePNGs)
        self.streamToDiskButton.clicked.connect(self.streamClick)
        self.streamBrowse.clicked.connect(self.browseForStream)
        self.clearImagesSignal.connect(self.clearAllImages)
        self.mp4Signal.connect(doneMP4)
        self.h5Signal.connect(doneH5)

        self.camera.addFrameListener(self.drawFrame)

        self.numberOfFrames.setValue(1)

        self.createParameters()

        self.writingMP4.setVisible(False)
        self.writingH5.setVisible(False)

        

    def browseForStream(self):

        file = QFileDialog.getSaveFileName()

        if not isinstance(file, str):
            file = file[0]

        if len(file) == 0:
            return
        
        self.streamFile.setText(file)


    def streamClick(self):

        if self.stream is None:

            self.streamFile.setDisabled(True)
            self.streamBrowse.setDisabled(True)

            self.streamPath = self.streamFile.text()
            self.stream     = self.camera.streamToFile(self.streamPath)

            self.streamToDiskButton.setChecked(True)

        else:

            self.stream.stop()
            self.stream = None

            original = self.streamToDiskButton.text()

            self.streamToDiskButton.setDisabled(True)
            self.mp4Button.setDisabled(True)
            self.h5Button.setDisabled(True)

            if self.mp4Button.isChecked():

                self.writingMP4.setVisible(True)

                def saveMP4():
                    self.camera.openFrameReader(self.streamPath).convertToMP4(self.streamPath + ".mp4")
                    self.mp4Signal.emit()

                self.pool.start(saveMP4)


            if self.h5Button.isChecked():

                self.writingH5.setVisible(True)

                def saveH5():

                    file   = h5py.File(self.streamPath + ".h5", "w")
                    reader = self.camera.openFrameReader(self.streamPath)

                    i = 0

                    while reader.hasFrame():

                        frame = reader.readFrame()
                        nm    = "Frame %d" % i

                        if isinstance(frame, Frame.IntFrame):
                            ds = file.create_dataset(nm, data=frame.image())
                        elif isinstance(frame, RGBFrame):
                            ds = file.create_dataset(nm, data=frame.getRGBImage())
                        elif isinstance(frame, U16RGBFrame):
                            ds = file.create_dataset(nm, data=frame.getRGBImage())
                        else:
                            ds = file.create_dataset(nm, data=frame.getARGBImage())

                        ds.attrs["Timestamp"] = frame.getTimestamp()

                        i += 1

                    file.close()
                    self.h5Signal.emit()


                self.pool.start(saveH5)


            self.streamToDiskButton.setText(original)

            if self.writingMP4.isVisible() or self.writingH5.isVisible():
                pass
            else:
                self.streamFile.setDisabled(False)
                self.streamBrowse.setDisabled(False)
                self.streamToDiskButton.setChecked(False)
                self.streamToDiskButton.setDisabled(False)
                self.mp4Button.setDisabled(False)
                self.h5Button.setDisabled(False)




    def createParameters(self):

        for param in self.camera.getAllParameters():

            w, g, s = self.createParameterWidget(param.getDefaultValue(), param.getChoices())

            if w is None:
                continue

            status = QPushButton()
            status.setIcon(self.warningIcon)
            status.setFixedSize(25, 25)
            status.setVisible(False)

            w.setContentsMargins(0, 0, 0, 0)
            hbox = QHBoxLayout()
            hbox.addWidget(w, 1)
            setB = QPushButton("✓")
            setB.setFixedWidth(25)
            hbox.addWidget(setB, 0, Qt.AlignTop)
            hbox.addWidget(status, 0, Qt.AlignTop)

            self.cameraParameters.addRow(param.getName(), hbox)

            s(param.getCurrentValue())

            setB.clicked.connect(lambda v, g=g, s=s, p=param, st=status: self.applyParameter(g, s, p, st, True))
            self.params.append((w, g, s, param, status))


    def updateTemperature(self):
        self.currentTemperature.display(self.camera.getControlledTemperature())


    def showException(self, e: Exception):
        self.errorMessage.showMessage(str(e))


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

        self.frames.clear()
        self.frames += frames

        self.captured.children().clear()

        for frame in frames:
            self.addFrame(frame)
        
        if not self.camera.isAcquiring():
            self.drawFrame(frames[len(frames) - 1])


    def clearAllImages(self):
        self.captured.clearImages()
        self.frames.clear()

    
    def live(self):

        if self.camera.isAcquiring():
            self.camera.stopAcquisition()
            self.liveViewButton.setChecked(False)
        else:
            self.camera.startAcquisition()
            self.liveViewButton.setChecked(True)


    def drawFrame(self, frame: Frame):

        if self.buffer is None or len(self.buffer) != frame.size():

            self.buffer  = frame.getARGBData()
            self._image   = QImage(self.buffer, frame.getWidth(), frame.getHeight(), QImage.Format.Format_ARGB32)

        else:
            frame.readARGBData(self.buffer)

        pixmap  = QPixmap(QImage(self.buffer, frame.getWidth(), frame.getHeight(), QImage.Format.Format_ARGB32))
        QImage(self.buffer, frame.getWidth(), frame.getHeight(), QImage.Format.Format_ARGB32)

        if self.crosshairButton.isChecked():

            painter = QPainter(pixmap)
            midX    = int(frame.getWidth() / 2)
            midY    = int(frame.getHeight() / 2)

            painter.setPen(QPen(Qt.white, self.crosshairPixels.value()))
            painter.drawLine(midX, 0, midX, frame.getHeight() - 1)
            painter.drawLine(0, midY, frame.getWidth() - 1, midY)
            painter.end()


        self.cameraImage.setPixmap(pixmap.scaled(self.cameraImage.width(), self.cameraImage.height(), Qt.KeepAspectRatio))


    def addFrame(self, frame: Frame):
    
        image = QImage(frame.getARGBData(), frame.getWidth(), frame.getHeight(), QImage.Format.Format_ARGB32)
        self.captured.addImage(image)


    def applyParameters(self):

        for (w, g, s, p, st) in self.params:
            self.applyParameter(g, s, p, st)

        self.refreshParameters()


    def applyParameter(self, getter: Callable, setter: Callable, param: Instrument.Parameter, status: QPushButton, refresh = False):

        status.setVisible(False)

        try:
            status.clicked.disconnect()
        except:
            pass

        try:
            param.set(getter())
        except Exception as e:
            status.clicked.connect(lambda v, e=e: self.showException(e))
            status.setVisible(True)

        if refresh:
            self.refreshParameters()


    def refreshParameters(self):

        for (w, g, s, p, st) in self.params:

            try:
                s(p.getCurrentValue())
            except Exception as e:
                print(e)


    def createParameterWidget(self, defaultValue, choices = []) -> Tuple[QWidget, Callable, Callable]:

        if type(defaultValue) == Instrument.AutoQuantity:

            checkBox               = QCheckBox("Auto")
            widget, getter, setter = self.createParameterWidget(defaultValue.getValue(), choices)

            if widget is None:
                return (None, None, None)

            widget.setDisabled(checkBox.isChecked())

            def updateCheckBox():
                widget.setDisabled(checkBox.isChecked())

            checkBox.stateChanged.connect(updateCheckBox)
            
            hbox = QHBoxLayout() if type(defaultValue.getValue()) not in [ResultList, ResultTable] else QVBoxLayout()
            cont = QWidget()
            cont.setLayout(hbox)
            cont.setContentsMargins(0, 0, 0, 0)
            hbox.setContentsMargins(0, 0, 0, 0)

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
            widget, getter, setter = self.createParameterWidget(defaultValue.getValue(), choices)

            if widget is None:
                return (None, None, None)

            widget.setDisabled(not checkBox.isChecked())

            def updateCheckBox():
                widget.setDisabled(not checkBox.isChecked())

            checkBox.stateChanged.connect(updateCheckBox)
            
            hbox = QHBoxLayout() if type(defaultValue.getValue()) not in [ResultList, ResultTable] else QVBoxLayout()
            cont = QWidget()
            cont.setLayout(hbox)
            cont.setContentsMargins(0, 0, 0, 0)
            hbox.setContentsMargins(0, 0, 0, 0)

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

            doubleBox = ScientificSpinBox()

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
        
        elif type(defaultValue) in [ResultTable, ResultList]:

            table = ResultTableWidget()
            table.setResultTable(defaultValue)

            return (table, table.getResultTable, table.setResultTable)

        else:
            
            return (None, None, None)
        

    def saveToH5(self):

        try:
            file = df.current()
        except:
            return

        def threadMethod():

            if "FastCameraData" in file:
                group = file["FastCameraData"]
            else:
                group = file.create_group("FastCameraData")

            i = 0

            for frame in self.frames:

                nm = "Captured Frame %d" % i

                while nm in group:
                    i += 1
                    nm = "Captured Frame %d" % i

                if isinstance(frame, Frame.IntFrame):
                    ds = group.create_dataset(nm, data=frame.image())
                elif isinstance(frame, RGBFrame):
                    ds = group.create_dataset(nm, data=frame.getRGBImage())
                elif isinstance(frame, U16RGBFrame):
                    ds = group.create_dataset(nm, data=frame.getRGBImage())
                else:
                    ds = group.create_dataset(nm, data=frame.getARGBImage())

                ds.attrs["Timestamp"] = frame.getTimestamp()

                for key, value in frame.getAttributes().items():
                    
                    if isinstance(value, Instrument.AutoQuantity):

                        ds.attrs[key + ": Auto"]  = value.isAuto()
                        value = value.getValue()
                        key   = key + ": Value"
                
                    if isinstance(value, Instrument.OptionalQuantity):

                        ds.attrs[key + ": Used"]  = value.isUsed()
                        value = value.getValue()
                        key   = key + ": Value"

                    if isinstance(value, ResultTable):

                        con = [[str(v) for v in r] for r in value.asStringArray()]
                        con = [[str(c.getTitle()) for c in value.getColumns()]] + con
                        ds.attrs[key] = con

                    else:
                        ds.attrs[key] = value


                i += 1


            file.flush()
            self.clearImagesSignal.emit()

        self.pool.start(threadMethod)


    def savePNGs(self):

        directory = QFileDialog.getExistingDirectory()

        if not isinstance(directory, str):
            directory = directory[0]

        if len(directory) == 0:
            return

        def threadMethod():

            i = 0

            for frame in self.frames:

                nm = "Captured Frame %d.jpg" % i

                while os.path.isfile(os.path.join(directory, nm)):
                    i += 1
                    nm = "Captured Frame %d.png" % i

                frame.savePNG(os.path.join(directory, nm))

                i += 1

            self.clearImagesSignal.emit()

        self.pool.start(threadMethod)
        