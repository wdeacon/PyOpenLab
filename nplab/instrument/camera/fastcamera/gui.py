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
from qtpy.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap, QResizeEvent
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
        
        # Hold onto camera
        self.camera = camera

        # Create buffers
        self.buffer                                  = None
        self.frames     : List[Frame]                = []
        self.params     : List[Instrument.Parameter] = []
        self.stream     : FrameThread                = None
        self.lastWidth  : int                        = None
        self.lastHeight : int                        = None

        # Define types for automatically linked widgets
        self.cameraParameters    : QVBoxLayout 
        self.numberOfFrames      : QSpinBox    
        self.captureButton       : QPushButton 
        self.liveViewButton      : QPushButton 
        self.cameraImage         : QLabel      
        self.capturedImages      : QGroupBox   
        self.clearImages         : QPushButton
        self.applyButton         : QPushButton
        self.refreshButton       : QPushButton
        self.statusGroup         : QGroupBox
        self.streamBox           : QGroupBox
        self.temperatureLabel    : QLabel
        self.currentTemperature  : QLCDNumber
        self.fpsCounter          : QLCDNumber
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
        self.deleteButton        : QPushButton
        self.namePattern         : QLineEdit
         
        # Load UI from file
        uic.loadUi((os.path.dirname(__file__) + '/resources/fcgui.ui'), self)

        # Create other QT elements
        self.captured     = ImageListWidget()
        self.pool         = QThreadPool()
        self.errorMessage = QErrorMessage()

        self.capturedImages.layout().addWidget(self.captured)
            
        self.setupStatusMonitoring()
        self.setupStreamer()
        self.setupConnections()
        self.setupParameters()

        self.camera.addFrameListener(self.drawFrame)


    def setupStatusMonitoring(self):

        self.timer = QTimer()
        self.timer.setInterval(1000)

        # Check if the camera implements some sort of temperature control
        if isinstance(self.camera, TemperatureControlled):
            self.timer.timeout.connect(self.updateTemperature)
            self.currentTemperature.setEnabled(True)
            self.temperatureLabel.setEnabled(True)

        else:
            self.currentTemperature.setEnabled(False)
            self.temperatureLabel.setEnabled(False)

        self.timer.timeout.connect(self.updateFPS)
        self.timer.start()


    def updateFPS(self):
        self.fpsCounter.display(self.camera.getAcquisitionFPS())

    
    def setupStreamer(self):

        self.writingMP4.setVisible(False)
        self.writingH5.setVisible(False)

        def reEnable():

            if not (self.writingMP4.isVisible() or self.writingH5.isVisible()):

                if self.deleteButton.isChecked():
                    os.remove(self.streamPath)

                self.streamFile.setDisabled(False)
                self.streamBrowse.setDisabled(False)
                self.streamToDiskButton.setDisabled(False)
                self.mp4Button.setDisabled(False)
                self.h5Button.setDisabled(False)
                self.deleteButton.setDisabled(False)
                self.streamToDiskButton.setStyleSheet("")
                self.streamToDiskButton.setText("Start Streaming to Disk")


        def doneMP4():
            self.writingMP4.setVisible(False)
            reEnable()


        def doneH5():
            self.writingH5.setVisible(False)
            reEnable()

        
        def checkDelete():

            if self.mp4Button.isChecked() or self.h5Button.isChecked():
                self.deleteButton.setDisabled(False)
            else:
                self.deleteButton.setChecked(False)
                self.deleteButton.setDisabled(True)

            if self.mp4Button.isChecked():
                self.mp4Button.setStyleSheet("background: teal;")
            else:
                self.mp4Button.setStyleSheet("")

            if self.h5Button.isChecked():
                self.h5Button.setStyleSheet("background: orange;")
            else:
                self.h5Button.setStyleSheet("")

            if self.deleteButton.isChecked():
                self.deleteButton.setStyleSheet("background: brown;")
            else:
                self.deleteButton.setStyleSheet("")


        self.mp4Signal.connect(doneMP4)
        self.h5Signal.connect(doneH5)
        self.mp4Button.clicked.connect(checkDelete)
        self.h5Button.clicked.connect(checkDelete)
        self.deleteButton.clicked.connect(checkDelete)

    def resizeEvent(self, a0):
        self.redrawFrame()
        return super().resizeEvent(a0)

    def setupConnections(self):

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
        self.crosshairButton.clicked.connect(self.crosshairClick)


    def crosshairClick(self):

        if self.crosshairButton.isChecked():
            self.crosshairButton.setText("Hide Crosshair")
        else:
            self.crosshairButton.setText("Show Crosshair")

        self.redrawFrame()


    def browseForStream(self):

        file = QFileDialog.getSaveFileName()

        if not isinstance(file, str):
            file = file[0]

        if len(file) == 0:
            return
        
        self.streamFile.setText(file)


    def streamClick(self):

        if self.stream is None:

            if str(self.streamFile.text()).strip() == "":
                self.errorMessage.showMessage("You must choose a file to output to before starting the stream.")
                return


            self.streamFile.setDisabled(True)
            self.streamBrowse.setDisabled(True)

            self.streamAttrs = self.camera.getAllParametersAsMap()
            self.streamPath  = self.streamFile.text()
            self.stream      = self.camera.streamToFile(self.streamPath)

            self.streamToDiskButton.setStyleSheet("background: brown;")
            self.streamToDiskButton.setText("Stop Streaming")

        else:

            self.stream.stop()
            self.stream = None

            self.streamToDiskButton.setDisabled(True)
            self.mp4Button.setDisabled(True)
            self.h5Button.setDisabled(True)
            self.deleteButton.setDisabled(True)
            self.streamToDiskButton.setText("Converting...")
            self.streamToDiskButton.setStyleSheet("background: orange;")

            if self.mp4Button.isChecked():

                self.writingMP4.setVisible(True)

                def saveMP4():

                    try:
                        self.camera.openFrameReader(self.streamPath).convertToMP4(self.streamPath + ".mp4")
                    finally:
                        self.mp4Signal.emit()

                self.pool.start(saveMP4)


            if self.h5Button.isChecked():

                self.writingH5.setVisible(True)

                def saveH5():

                    try:
                        
                        file = df.current()

                        j = 0
                        nm = "Stream %d" % j

                        while nm in file:
                            j += 1
                            nm = "Stream %d" % j

                        group  = file.create_group(nm)

                        for key, value in self.streamAttrs.items():
                            
                            if isinstance(value, Instrument.AutoQuantity):

                                group.attrs[key + ": Auto"]  = value.isAuto()
                                value = value.getValue()
                                key   = key + ": Value"
                        

                            if isinstance(value, Instrument.OptionalQuantity):

                                group.attrs[key + ": Used"]  = value.isUsed()
                                value = value.getValue()
                                key   = key + ": Value"


                            if isinstance(value, ResultTable):

                                con = [[str(v) for v in r] for r in value.asStringArray()]
                                con = [[str(c.getTitle()) for c in value.getColumns()]] + con
                                group.attrs[key] = con

                            else:
                                group.attrs[key] = str(value)


                        reader = self.camera.openFrameReader(self.streamPath)

                        i = 0

                        while reader.hasFrame():

                            frame = reader.readFrame()
                            nm    = "frame_%d" % i

                            if isinstance(frame, Frame.IntFrame):
                                ds = group.create_dataset(nm, data=frame.image())
                            elif isinstance(frame, RGBFrame):
                                ds = group.create_dataset(nm, data=frame.getRGBImage())
                            elif isinstance(frame, U16RGBFrame):
                                ds = group.create_dataset(nm, data=frame.getRGBImage())
                            else:
                                ds = group.create_dataset(nm, data=frame.getARGBImage())

                            ds.attrs["Timestamp"] = frame.getTimestamp()

                            i += 1

                    finally:
                        self.h5Signal.emit()


                self.pool.start(saveH5)

            if not (self.writingMP4.isVisible() or self.writingH5.isVisible()):

                if self.deleteButton.isChecked():
                    os.remove(self.streamPath)

                self.streamFile.setDisabled(False)
                self.streamBrowse.setDisabled(False)
                self.streamToDiskButton.setDisabled(False)
                self.mp4Button.setDisabled(False)
                self.h5Button.setDisabled(False)
                self.deleteButton.setDisabled(False)
                self.streamToDiskButton.setStyleSheet("")
                self.streamToDiskButton.setText("Start Streaming to Disk")



    def setupParameters(self):

        forms = {"General": QFormLayout()}

        for param in self.camera.getAllParameters():

            group = param.getGroup() if param.isGrouped() else "General"

            if group not in forms:
                forms[group] = QFormLayout()

            form = forms[group]

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

            form.addRow(param.getName(), hbox)

            s(param.getCurrentValue())

            setB.clicked.connect(lambda v, g=g, s=s, p=param, st=status: self.applyParameter(g, s, p, st, True))
            self.params.append((w, g, s, param, status))

        for name, form in forms.items():
            box = QGroupBox(name)
            box.setLayout(form)
            self.cameraParameters.addWidget(box)

    def updateTemperature(self):
        self.currentTemperature.display(self.camera.getControlledTemperature())


    def showException(self, e: Exception):
        self.errorMessage.showMessage(str(e))


    def intTime(self):
        self.camera.setIntegrationTime(self.exposureTime.value())


    def capture(self):

        self.captureButton.setDisabled(True)
        self.captureButton.setText("Capturing...")
        self.captureButton.setStyleSheet("background: brown;")

        def doCapture():
            frames = self.camera.getFrameSeries(self.numberOfFrames.value())
            self.captureCompleteSignal.emit(list(frames))

        self.pool.start(doCapture)


    def captureComplete(self, frames):

        self.captureButton.setDisabled(False)
        self.captureButton.setText("Capture")
        self.captureButton.setStyleSheet("")

        self.frames.clear()
        self.frames += frames

        self.captured.children().clear()

        for frame in frames:
            self.addFrame(frame)
        
        if not self.camera.isAcquiring():
            self.drawFrame(frames[len(frames) - 1])


    def clearAllImages(self):

        self.writeImages.setDisabled(True)
        self.saveImages.setDisabled(True)
        self.clearImages.setDisabled(True)

        self.captured.clearImages()
        self.frames.clear()

        self.writeImages.setDisabled(False)
        self.saveImages.setDisabled(False)
        self.clearImages.setDisabled(False)

    
    def live(self):

        if self.camera.isAcquiring():
            self.camera.stopAcquisition()
            self.liveViewButton.setStyleSheet("")
            self.liveViewButton.setText("Start Continuous Acquisition")
        else:
            self.camera.startAcquisition()
            self.liveViewButton.setStyleSheet("background: brown;")
            self.liveViewButton.setText("Stop Continuous Acquisition")


    def drawFrame(self, frame: Frame):

        if self.buffer is None or len(self.buffer) != frame.size():
            self.buffer     = frame.getARGBData()
            self.lastWidth  = frame.getWidth()
            self.lastHeight = frame.getHeight()
        else:
            frame.readARGBData(self.buffer)

        pixmap = QPixmap(QImage(self.buffer, self.lastWidth, self.lastHeight, QImage.Format.Format_ARGB32))

        if self.crosshairButton.isChecked():

            painter = QPainter(pixmap)
            midX    = int(self.lastWidth / 2)
            midY    = int(self.lastHeight  / 2)

            painter.setPen(QPen(Qt.white, self.crosshairPixels.value()))
            painter.drawLine(midX, 0, midX, self.lastHeight - 1)
            painter.drawLine(0, midY, self.lastWidth - 1, midY)
            painter.end()


        self.cameraImage.setPixmap(pixmap.scaled(self.cameraImage.width(), self.cameraImage.height(), Qt.KeepAspectRatio))

        if self.camera.isAcquiring():
            self.liveViewButton.setStyleSheet("background: brown;")
            self.liveViewButton.setText("Stop Continuous Acquisition")
        else:
            self.liveViewButton.setStyleSheet("")
            self.liveViewButton.setText("Start Continuous Acquisition")
            


    def redrawFrame(self):

        if self.lastWidth is None or self.lastHeight is None:
            return

        pixmap = QPixmap(QImage(self.buffer, self.lastWidth, self.lastHeight, QImage.Format.Format_ARGB32))

        if self.crosshairButton.isChecked():

            painter = QPainter(pixmap)
            midX    = int(self.lastWidth / 2)
            midY    = int(self.lastHeight  / 2)

            painter.setPen(QPen(Qt.white, self.crosshairPixels.value()))
            painter.drawLine(midX, 0, midX, self.lastHeight - 1)
            painter.drawLine(0, midY, self.lastWidth - 1, midY)
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

        running = self.camera.isAcquiring()

        if running:
            self.camera.stopAcquisition()

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

        if running:
            self.camera.startAcquisition()



    def refreshParameters(self):

        for (w, g, s, p, st) in self.params:

            try:
                s(p.getCurrentValue())
            except Exception as e:
                print(e)


    def createParameterWidget(self, defaultValue, choices = []) -> Tuple[QWidget, Callable, Callable]:

        if isinstance(defaultValue, Instrument.AutoQuantity):

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
        
        elif isinstance(defaultValue, Instrument.OptionalQuantity):

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

            def getter(choices=choices, choiceBox=choiceBox):
                return choices[choiceBox.currentIndex()]
            
            def setter(value):
                choiceBox.setCurrentText(str(value))

            return (choiceBox, getter, setter)
        
        elif isinstance(defaultValue, (Double, float)):

            doubleBox = ScientificSpinBox()

            return (doubleBox, doubleBox.value, doubleBox.setValue)

        elif isinstance(defaultValue, (int, Integer)):

            intBox = QSpinBox()
            intBox.setMinimum(-2147483647)
            intBox.setMaximum(2147483647)

            return (intBox, lambda: np.int32(intBox.value()), intBox.setValue)
        
        elif isinstance(defaultValue, (bool, Boolean)):

            checkBox = QCheckBox()

            return (checkBox, checkBox.isChecked, checkBox.setChecked)
        
        elif isinstance(defaultValue, (str, String)):

            textBox = QLineEdit()

            return (textBox, textBox.text, textBox.setText)
        
        elif isinstance(defaultValue, ResultTable):

            table = ResultTableWidget()
            table.setResultTable(defaultValue)

            return (table, table.getResultTable, table.setResultTable)

        else:
            
            return (None, None, None)
        

    def saveToH5(self):

        self.writeImages.setDisabled(True)
        self.saveImages.setDisabled(True)
        self.clearImages.setDisabled(True)

        try:
            file = df.current()
        except:
            return


        def threadMethod():

            if "FastCameraData" in file:
                group = file["FastCameraData"]
            else:
                group = file.create_group("FastCameraData")


            pattern = self.namePattern.text()

            if r"%d" not in pattern and r"%s" not in pattern:
                pattern = pattern + r" %d"

            i = 0

            for frame in self.frames:

                nm = pattern % i

                while nm in group:
                    i += 1
                    nm = pattern % i


                if isinstance(frame, (Frame.ShortFrame, Frame.IntFrame, Frame.LongFrame)):
                    ds = group.create_dataset(nm, data=frame.image())
                elif isinstance(frame, (RGBFrame, U16RGBFrame)):
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
                        ds.attrs[key] = str(value)


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

        self.writeImages.setDisabled(True)
        self.saveImages.setDisabled(True)
        self.clearImages.setDisabled(True)

        def threadMethod():

            i = 0

            pattern = self.namePattern.text()

            if r"%d" not in pattern and r"%s" not in pattern:
                pattern = pattern + r" %d"

            pattern += ".png"

            for frame in self.frames:

                nm = pattern % i

                while os.path.isfile(os.path.join(directory, nm)):
                    i += 1
                    nm = pattern % i

                frame.savePNG(os.path.join(directory, nm))

                i += 1

            self.clearImagesSignal.emit()

        self.pool.start(threadMethod)
        