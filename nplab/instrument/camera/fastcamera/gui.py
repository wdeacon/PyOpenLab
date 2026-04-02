from threading import Lock

import h5py
import pyjisa.autoload
import os
import numpy as np

from typing import Callable, Dict, Generic, List, Tuple, TypeVar, Union

from jisa.devices              import Instrument
from jisa.devices.camera       import Camera as JCamera
from jisa.devices.camera.frame import Frame, FrameThread, RGBFrame, U16RGBFrame
from jisa.devices.features     import TemperatureControlled
from jisa                      import Util

from qtpy import uic
from qtpy.QtCore import QTimer, Qt, QThreadPool, Signal
from qtpy.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap, QResizeEvent
from qtpy.QtWidgets import *

from nplab.instrument.camera.fastcamera.datastream import DataStreamGUI
from nplab.instrument.camera.fastcamera.widgets import *

import nplab.datafile as df


C = TypeVar("C", bound=JCamera)

class FastCameraGUI(QWidget, Generic[C]):

    frameCapturedSignal   = Signal(Frame)
    captureCompleteSignal = Signal()
    captureWritingSignal  = Signal()
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
        self.delayTime           : QSpinBox
        self.captureButton       : QPushButton 
        self.liveViewButton      : QPushButton 
        self.cameraImage         : QLabel      
        self.applyButton         : QPushButton
        self.refreshButton       : QPushButton
        self.statusGroup         : QGroupBox
        self.streamBox           : QGroupBox
        self.temperatureLabel    : QLabel
        self.currentTemperature  : QLCDNumber
        self.fpsCounter          : QLCDNumber
        self.crosshairButton     : QPushButton
        self.crosshairPixels     : QSpinBox
        self.h5SaveButton        : QPushButton
        self.pngSaveButton       : QPushButton
        self.streamToDiskButton  : QPushButton
        self.streamFile          : QLineEdit
        self.streamBrowse        : QPushButton
        self.mp4Button           : QPushButton
        self.h5Button            : QPushButton
        self.gifButton           : QPushButton
        self.writingMP4          : QLabel
        self.writingH5           : QLabel
        self.deleteButton        : QPushButton
        self.namePattern         : QLineEdit
        self.pngLabel            : QLabel
        self.pngDirectory        : QLineEdit
        self.pngBrowse           : QPushButton
        self.capturedImages      : QGroupBox
        self.h5Label             : QLabel
        self.h5Group             : QLineEdit
        self.countLabel          : QLabel
        self.delayLabel          : QLabel
         
        # Load UI from file
        uic.loadUi((os.path.dirname(__file__) + '/resources/fcgui.ui'), self)

        # Create other QT elements
        self.pool         = QThreadPool()
        self.errorMessage = QErrorMessage()
        self.bufferLuck   = Lock()


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


    def setupConnections(self):

        self.captureButton.clicked.connect(self.capture)
        self.liveViewButton.clicked.connect(self.live)
        self.frameCapturedSignal.connect(self.drawFrame)
        self.captureWritingSignal.connect(lambda: self.captureButton.setText("Writing..."))
        self.captureCompleteSignal.connect(self.captureComplete)
        self.applyButton.clicked.connect(self.applyParameters)
        self.refreshButton.clicked.connect(self.refreshParameters)
        self.streamToDiskButton.clicked.connect(self.streamClick)
        self.streamBrowse.clicked.connect(self.browseForStream)
        self.crosshairButton.clicked.connect(self.crosshairClick)
        self.h5SaveButton.clicked.connect(self.updateSaveButtons)
        self.pngSaveButton.clicked.connect(self.updateSaveButtons)
        self.pngBrowse.clicked.connect(self.browsePNGDirectory)


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
                self.gifButton.setDisabled(False)
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

            checked = False

            if self.mp4Button.isChecked():
                self.mp4Button.setStyleSheet("background: teal;")
                checked = True
            else:
                self.mp4Button.setStyleSheet("")

            if self.h5Button.isChecked():
                self.h5Button.setStyleSheet("background: purple;")
                checked = True
            else:
                self.h5Button.setStyleSheet("")

            if self.gifButton.isChecked():
                self.gifButton.setStyleSheet("background: navy;")
                checked = True
            else:
                self.gifButton.setStyleSheet("")

            if self.deleteButton.isChecked():
                self.deleteButton.setStyleSheet("background: brown;")
            else:
                self.deleteButton.setStyleSheet("")

            if checked:
                self.deleteButton.setDisabled(False)
            else:
                self.deleteButton.setChecked(False)
                self.deleteButton.setDisabled(True)


        self.mp4Signal.connect(doneMP4)
        self.h5Signal.connect(doneH5)
        self.mp4Button.clicked.connect(checkDelete)
        self.h5Button.clicked.connect(checkDelete)
        self.gifButton.clicked.connect(checkDelete)
        self.deleteButton.clicked.connect(checkDelete)


    def resizeEvent(self, a0):
        self.redrawFrame()
        return super().resizeEvent(a0)


    def updateFPS(self):
        self.fpsCounter.display(self.camera.getAcquisitionFPS())


    def updateSaveButtons(self):

        if self.h5SaveButton.isChecked():
            self.h5SaveButton.setStyleSheet("background: purple;")
            self.h5Group.setEnabled(True)
            self.h5Label.setEnabled(True)
        else:
            self.h5SaveButton.setStyleSheet("")
            self.h5Group.setEnabled(False)
            self.h5Label.setEnabled(False)


        if self.pngSaveButton.isChecked():
            self.pngSaveButton.setStyleSheet("background: teal;")
            self.pngLabel.setEnabled(True)
            self.pngDirectory.setEnabled(True)
            self.pngBrowse.setEnabled(True)
        else:
            self.pngSaveButton.setStyleSheet("")
            self.pngLabel.setEnabled(False)
            self.pngDirectory.setEnabled(False)
            self.pngBrowse.setEnabled(False)


    def browsePNGDirectory(self):

        file = QFileDialog.getExistingDirectory()

        if not isinstance(file, str):
            file = file[0]

        if len(file) == 0:
            return
        
        self.pngDirectory.setText(file)


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
            self.streamToDiskButton.setStyleSheet("")

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

                        self.writeAttributes(group, self.streamAttrs)

                        reader = self.camera.openFrameReader(self.streamPath)

                        i = 0

                        while reader.hasFrame():
                            self.frameToDataset(group, reader.readFrame(), r"frame_%d", i)
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



    def updateTemperature(self):
        self.currentTemperature.display(self.camera.getControlledTemperature())


    def showException(self, e: Exception):
        self.errorMessage.showMessage(str(e))


    def intTime(self):
        self.camera.setIntegrationTime(self.exposureTime.value())


    def capture(self):

        # Lock down the GUI inputs
        self.captureButton.setDisabled(True)
        self.capturedImages.setDisabled(True)
        self.countLabel.setDisabled(True)
        self.numberOfFrames.setDisabled(True)
        self.delayLabel.setDisabled(True)
        self.delayTime.setDisabled(True)
        self.captureButton.setText("Capturing...")
        self.captureButton.setStyleSheet("background: brown;")

        # Define what we want to happen
        def doCapture():

            output = not self.camera.isAcquiring()

            try:

                delay  = max(self.delayTime.value(), 0)
                count  = max(self.numberOfFrames.value(), 1)
                frames = []

                frame = self.camera.getFrame()
                frames.append(frame)

                if output:
                    self.frameCapturedSignal.emit(frame)

                for i in range(count - 1):

                    Util.sleep(delay)

                    frame = self.camera.getFrame()
                    frames.append(frame)

                    if output and not self.bufferLuck.locked():
                        self.frameCapturedSignal.emit(frame)


                if self.h5SaveButton.isChecked():
                    self.captureWritingSignal.emit()
                    self.saveToH5(frames)

                if self.pngSaveButton.isChecked():
                    self.captureWritingSignal.emit()
                    self.savePNGs(frames)

            finally:
                # When done, we need to signal the GUI to re-enable everything
                self.captureCompleteSignal.emit()


        # Give the method to our thread pool to execute in the background
        self.pool.start(doCapture)


    def captureComplete(self):

        self.captureButton.setDisabled(False)
        self.captureButton.setText("Capture")
        self.captureButton.setStyleSheet("")
        self.capturedImages.setDisabled(False)
        self.countLabel.setDisabled(False)
        self.numberOfFrames.setDisabled(False)
        self.delayLabel.setDisabled(False)
        self.delayTime.setDisabled(False)

    
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

        # So that we don't have multiple threads trying to access the buffer at the same time
        with self.bufferLuck:

            try:

                # If the frame size has changed, then we need to recreate the buffer, otherwise we should reuse it
                if self.buffer is None or len(self.buffer) != frame.size():
                    self.buffer = frame.getARGBData()
                else:
                    frame.readARGBData(self.buffer)

                # Record dimensions incase we need to redraw before a new frame comes in
                self.lastWidth  = frame.getWidth()
                self.lastHeight = frame.getHeight()

                # Convert the buffer into a pixmap
                pixmap = QPixmap(QImage(self.buffer, self.lastWidth, self.lastHeight, QImage.Format.Format_ARGB32))

                # If crosshair is enabled, then paint one on top of the image in the pixmap
                if self.crosshairButton.isChecked():

                    painter = QPainter(pixmap)
                    midX    = int(self.lastWidth / 2)
                    midY    = int(self.lastHeight  / 2)

                    painter.setPen(QPen(Qt.white, self.crosshairPixels.value()))
                    painter.drawLine(midX, 0, midX, self.lastHeight - 1)
                    painter.drawLine(0, midY, self.lastWidth - 1, midY)
                    painter.end()


                # Display the pixmap, scaled to the size of the GUI element at this moment
                self.cameraImage.setPixmap(pixmap.scaled(self.cameraImage.width(), self.cameraImage.height(), Qt.KeepAspectRatio))
                self.cameraImage.update()

            except:
                print("Exception when drawing frame")

            finally:
                # Limit display to 100 Hz. Anything more is just excessive.
                Util.sleep(10)


    def redrawFrame(self):

        # So that we don't have multiple threads trying to access the buffer at the same time
        with self.bufferLuck:

            try:

                # If these haven't been set, then we can't possibly redraw, so give up
                if self.lastWidth is None or self.lastHeight is None:
                    return

                # Convert the buffer into a pixmap
                pixmap = QPixmap(QImage(self.buffer, self.lastWidth, self.lastHeight, QImage.Format.Format_ARGB32))

                # If crosshair is enabled, then paint one on top of the image in the pixmap
                if self.crosshairButton.isChecked():

                    painter = QPainter(pixmap)
                    midX    = int(self.lastWidth / 2)
                    midY    = int(self.lastHeight  / 2)

                    painter.setPen(QPen(Qt.white, self.crosshairPixels.value()))
                    painter.drawLine(midX, 0, midX, self.lastHeight - 1)
                    painter.drawLine(0, midY, self.lastWidth - 1, midY)
                    painter.end()


                # Display the pixmap, scaled to the size of the GUI element at this moment
                self.cameraImage.setPixmap(pixmap.scaled(self.cameraImage.width(), self.cameraImage.height(), Qt.KeepAspectRatio))   
                self.cameraImage.update()

            except:
                print("Exception when redrawing frame")

            finally:
                # Limit display to 100 Hz. Anything more is just excessive.
                Util.sleep(10)


    def applyParameters(self):
        '''Applies all configuration parameters, then updates their displayed values'''

        running = self.camera.isAcquiring()

        if running:
            self.camera.stopAcquisition()

        for (w, g, s, p, st) in self.params:
            self.applyParameter(g, s, p, st)

        self.refreshParameters()

        if running:
            self.camera.startAcquisition()


    def applyParameter(self, getter: Callable, setter: Callable, param: Instrument.Parameter, status: QPushButton, refresh = False):
        '''Applies one single parameter, optionally can refresh all others afterwards if specified'''

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


    def createParameterWidget(self, defaultValue, choices: List = []) -> Tuple[QWidget, Callable, Callable]:

        if isinstance(defaultValue, Instrument.AutoQuantity):

            checkBox = QCheckBox("Auto")
            checkBox.setChecked(defaultValue.isAuto())

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

            checkBox = QCheckBox("Enabled")
            checkBox.setChecked(defaultValue.isUsed())
            
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
            choiceBox.addItems([str(c) for c in choices])

            def getter(choices=choices, choiceBox=choiceBox):
                return choices[choiceBox.currentIndex()]
            
            def setter(value):
                choiceBox.setCurrentIndex(choices.index(value))

            setter(defaultValue)

            return (choiceBox, getter, setter)
        
        elif isinstance(defaultValue, (Double, float)):

            doubleBox = ScientificSpinBox()
            doubleBox.setValue(defaultValue)

            return (doubleBox, doubleBox.value, doubleBox.setValue)

        elif isinstance(defaultValue, (int, Integer)):

            intBox = QSpinBox()
            intBox.setMinimum(-2147483647)
            intBox.setMaximum(2147483647)
            intBox.setValue(defaultValue)

            return (intBox, lambda: np.int32(intBox.value()), intBox.setValue)
        
        elif isinstance(defaultValue, (bool, Boolean)):

            checkBox = QCheckBox()
            checkBox.setChecked(defaultValue)
            return (checkBox, checkBox.isChecked, checkBox.setChecked)
        
        elif isinstance(defaultValue, (str, String)):

            textBox = QLineEdit()
            textBox.setText(str(defaultValue))

            return (textBox, textBox.text, textBox.setText)
        
        elif isinstance(defaultValue, ResultTable):

            table = ResultTableWidget()
            table.setResultTable(defaultValue)

            return (table, table.getResultTable, table.setResultTable)

        else:
            
            return (None, None, None)
        

    def saveToH5(self, frames):

        try:
            file = df.current()
        except:
            QErrorMessage.showMessage("No HDF5 data file currently open to save to.")
            return

        try:

            groupName = self.h5Group.text().strip("/")
            parts     = [p for p in groupName.split("/") if p.strip() != ""]
            group     = file
            counter   = 0

            # Traverse through path specified by user
            for part in parts:

                if part in group:
                    group = group[part]
                else:
                    group = group.create_group(part)


            pattern = self.namePattern.text()

            # Check that the pattern has a format specifier in it
            try:
                pattern % 1
            except:
                pattern += r"_%d"

            for frame in frames:
                self.frameToDataset(group, frame, pattern, counter)
                counter += 1

        finally:

            file.flush()


    def frameToDataset(self, group: h5py.Group, frame: Frame, pattern: str, counter: int = 0) -> h5py.Dataset:
        
        name = pattern % counter

        while name in group:
            counter += 1
            name     = pattern % counter


        if isinstance(frame, (Frame.ShortFrame, Frame.IntFrame, Frame.LongFrame)):
            ds = group.create_dataset(name, data=frame.image())
        elif isinstance(frame, (RGBFrame, U16RGBFrame)):
            ds = group.create_dataset(name, data=frame.getRGBImage())
        else:
            ds = group.create_dataset(name, data=frame.getARGBImage())

        self.writeAttributes(ds, frame)

        return ds


    def writeAttributes(self, ds: h5py.HLObject, data: Union[Dict[str, object], Frame]):

        if isinstance(data, Frame):
            ds.attrs["Timestamp"] = data.getTimestamp()
            data = data.getAttributes()

        for key, value in data.items():
            
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




    def savePNGs(self, frames):

        counter   = 0
        directory = self.pngDirectory.text()
        pattern   = self.namePattern.text()

        os.makedirs(directory, exist_ok=True)

        if r"%d" not in pattern and r"%s" not in pattern:
            pattern = pattern + r" %d"

        pattern += ".png"

        for frame in frames:

            nm = pattern % counter

            while os.path.isfile(os.path.join(directory, nm)):
                counter += 1
                nm = pattern % counter

            frame.savePNG(os.path.join(directory, nm))

            counter += 1

        