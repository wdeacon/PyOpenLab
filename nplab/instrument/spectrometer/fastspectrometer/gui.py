from threading import Lock

import h5py
import pyjisa.autoload
import os
import numpy as np

from typing import Callable, Dict, Generic, List, Tuple, TypeVar, Union

from jisa.results                       import ResultTable
from jisa.devices                       import Instrument
from jisa.devices.spectrometer          import CameraSpectrometer, Spectrometer as JSpectrometer
from jisa.devices.spectrometer.spectrum import Spectrum, SpectrumReader, SpectrumThread
from jisa.devices.features              import TemperatureControlled
from jisa                               import Util

from qtpy import uic
from qtpy.QtCore import QTimer, Qt, QThreadPool, Signal
from qtpy.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap, QResizeEvent
from qtpy.QtWidgets import *


import nplab.datafile as df

import pyqtgraph as pg

from nplab.instrument.spectrometer.fastspectrometer.csconfig import CSConfigGUI
from nplab.ui.widgets.jisa import JISAConfigPanel

S = TypeVar("S", bound=JSpectrometer)

class FastSpectrometerGUI(QWidget, Generic[S]):

    spectrumSignal        = Signal(Spectrum)
    progressSignal        = Signal(float)
    captureCompleteSignal = Signal()
    captureWritingSignal  = Signal()
    mp4Signal             = Signal()
    h5Signal              = Signal()
    warningIcon           = QIcon.fromTheme("dialog-warning")

    def __init__(self, spectrometer: S):

        super().__init__()
        
        # Hold onto camera
        self.spectrometer = spectrometer

        # Create buffers
        self.buffer                                  = None
        self.params     : List[Instrument.Parameter] = []
        self.stream     : SpectrumThread             = None
        self.lastWidth  : int                        = None
        self.lastHeight : int                        = None

        # Define types for automatically linked widgets
        self.cameraParameters   : QVBoxLayout 
        self.numberOfFrames     : QSpinBox    
        self.delayTime          : QSpinBox
        self.captureButton      : QPushButton 
        self.liveViewButton     : QPushButton 
        self.spectrumGroup      : QGroupBox      
        self.applyButton        : QPushButton
        self.refreshButton      : QPushButton
        self.statusGroup        : QGroupBox
        self.streamBox          : QGroupBox
        self.temperatureLabel   : QLabel
        self.currentTemperature : QLCDNumber
        self.fpsCounter         : QLCDNumber
        self.h5SaveButton       : QPushButton
        self.streamToDiskButton : QPushButton
        self.streamFile         : QLineEdit
        self.streamBrowse       : QPushButton
        self.h5Button           : QPushButton
        self.writingH5          : QLabel
        self.deleteButton       : QPushButton
        self.namePattern        : QLineEdit
        self.capturedImages     : QGroupBox
        self.h5Label            : QLabel
        self.h5Group            : QLineEdit
        self.countLabel         : QLabel
        self.delayLabel         : QLabel
        self.configBox          : QGroupBox
        self.progressBar        : QProgressBar
         
        # Load UI from file
        uic.loadUi((os.path.dirname(__file__) + '/resources/fsgui.ui'), self)

        # Create other QT elements
        self.pool         = QThreadPool()
        self.errorMessage = QErrorMessage()
        self.bufferLock   = Lock()
        self.plot         = pg.plot(title="Spectrum", left="Counts", bottom="Wavelength [m]")
        self.plotData     = self.plot.plotItem.plot([],[])
        self.configPanel  = JISAConfigPanel(self.spectrometer)

        self.configBox.layout().addWidget(self.configPanel)

        if isinstance(self.spectrometer, CameraSpectrometer):
            self.csconfig = CSConfigGUI(self.spectrometer)
            self.csbutton = QPushButton("Configure Transformation...")
            self.csbutton.clicked.connect(self.csconfig.show)
            self.configBox.layout().addWidget(self.csbutton)

        self.spectrumGroup.layout().addWidget(self.plot)

        self.progressBar.setVisible(False)

        self.setupStatusMonitoring()
        self.setupStreamer()
        self.setupConnections()

        self.spectrometer.addSpectrumListener(self.drawSpectrum)
        self.spectrometer.addAcquisitionListener(self.updateAcquisition)


    def setupStatusMonitoring(self):

        self.timer = QTimer()
        self.timer.setInterval(1000)

        # Check if the camera implements some sort of temperature control
        if isinstance(self.spectrometer, TemperatureControlled):
            self.timer.timeout.connect(self.updateTemperature)
            self.currentTemperature.setEnabled(True)
            self.temperatureLabel.setEnabled(True)

        else:
            self.currentTemperature.setEnabled(False)
            self.temperatureLabel.setEnabled(False)


        self.timer.start()


    def setupConnections(self):

        self.captureButton.clicked.connect(self.capture)
        self.liveViewButton.clicked.connect(self.live)
        self.spectrumSignal.connect(self.doDraw)
        self.captureWritingSignal.connect(lambda: self.captureButton.setText("Writing..."))
        self.captureCompleteSignal.connect(self.captureComplete)
        self.streamToDiskButton.clicked.connect(self.streamClick)
        self.streamBrowse.clicked.connect(self.browseForStream)
        self.h5SaveButton.clicked.connect(self.updateSaveButtons)
        self.progressSignal.connect(self.updateProgress)
    
    def setupStreamer(self):

        self.writingH5.setVisible(False)

        def reEnable():

            if not self.writingH5.isVisible():

                if self.deleteButton.isChecked():
                    os.remove(self.streamPath)

                self.streamFile.setDisabled(False)
                self.streamBrowse.setDisabled(False)
                self.streamToDiskButton.setDisabled(False)
                self.h5Button.setDisabled(False)
                self.deleteButton.setDisabled(False)
                self.streamToDiskButton.setStyleSheet("")
                self.streamToDiskButton.setText("Start Streaming to Disk")


        def doneH5():
            self.writingH5.setVisible(False)
            reEnable()

        
        def checkDelete():

            checked = False

            if self.h5Button.isChecked():
                self.h5Button.setStyleSheet("background: purple; color: white;")
                checked = True
            else:
                self.h5Button.setStyleSheet("")

            if checked:
                self.deleteButton.setDisabled(False)
            else:
                self.deleteButton.setChecked(False)
                self.deleteButton.setDisabled(True)

            if self.deleteButton.isChecked():
                self.deleteButton.setStyleSheet("background: brown; color: white;")
            else:
                self.deleteButton.setStyleSheet("")


        self.h5Signal.connect(doneH5)
        self.h5Button.clicked.connect(checkDelete)
        self.deleteButton.clicked.connect(checkDelete)


    def updateSaveButtons(self):

        if self.h5SaveButton.isChecked():
            self.h5SaveButton.setStyleSheet("background: purple; color: white;")
            self.h5Group.setEnabled(True)
            self.h5Label.setEnabled(True)
        else:
            self.h5SaveButton.setStyleSheet("")
            self.h5Group.setEnabled(False)
            self.h5Label.setEnabled(False)


    def browsePNGDirectory(self):

        file = QFileDialog.getExistingDirectory()

        if not isinstance(file, str):
            file = file[0]

        if len(file) == 0:
            return
        
        self.pngDirectory.setText(file)


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

            self.streamAttrs = self.spectrometer.getAllParametersAsMap()
            self.streamPath  = self.streamFile.text()
            self.stream      = self.spectrometer.streamToFile(self.streamPath)

            self.streamToDiskButton.setStyleSheet("background: brown; color: white;")
            self.streamToDiskButton.setText("Stop Streaming")

        else:

            self.stream.stop()
            self.stream = None

            self.streamToDiskButton.setDisabled(True)
            self.h5Button.setDisabled(True)
            self.deleteButton.setDisabled(True)
            self.streamToDiskButton.setText("Converting...")
            self.streamToDiskButton.setStyleSheet("")

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

                        reader = SpectrumReader(self.streamPath)

                        i = 0

                        while reader.hasSpectrum():
                            self.spectrumToDataset(group, reader.readSpectrum(), r"spectrum_%d", i)
                            i += 1

                    finally:
                        self.h5Signal.emit()


                self.pool.start(saveH5)

            if not self.writingH5.isVisible():

                if self.deleteButton.isChecked():
                    os.remove(self.streamPath)

                self.streamFile.setDisabled(False)
                self.streamBrowse.setDisabled(False)
                self.streamToDiskButton.setDisabled(False)
                self.h5Button.setDisabled(False)
                self.deleteButton.setDisabled(False)
                self.streamToDiskButton.setStyleSheet("")
                self.streamToDiskButton.setText("Start Streaming to Disk")



    def updateTemperature(self):
        self.currentTemperature.display(self.spectrometer.getControlledTemperature())


    def showException(self, e: Exception):
        self.errorMessage.showMessage(str(e))


    def capture(self):

        # Lock down the GUI inputs
        self.captureButton.setDisabled(True)
        self.capturedImages.setDisabled(True)
        self.liveViewButton.setVisible(False)
        self.countLabel.setDisabled(True)
        self.numberOfFrames.setDisabled(True)
        self.delayLabel.setDisabled(True)
        self.delayTime.setDisabled(True)
        self.captureButton.setText("Capturing...")
        self.captureButton.setStyleSheet("background: brown; color: white;")
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)
        self.configPanel.setDisabled(True)

        # Define what we want to happen
        def doCapture():

            output = not self.spectrometer.isAcquiring()

            try:

                delay   = max(self.delayTime.value(), 0)
                count   = max(self.numberOfFrames.value(), 1)
                spectra = []

                spectrum = self.spectrometer.getSpectrum()
                spectra.append(spectrum)

                if output and not self.bufferLock.locked():
                    self.spectrumSignal.emit(spectrum)

                self.progressSignal.emit(100.0 / count)

                for i in range(count - 1):

                    Util.sleep(delay)

                    spectrum = self.spectrometer.getSpectrum()
                    spectra.append(spectrum)

                    if output and not self.bufferLock.locked():
                        self.spectrumSignal.emit(spectrum)

                    self.progressSignal.emit(100.0 * (i + 1) / count)


                self.progressSignal.emit(100.0)

                if self.h5SaveButton.isChecked():
                    self.captureWritingSignal.emit()
                    self.saveToH5(spectra)


            finally:
                # When done, we need to signal the GUI to re-enable everything
                self.captureCompleteSignal.emit()


        # Give the method to our thread pool to execute in the background
        self.pool.start(doCapture)

    def updateProgress(self, value: float):
        self.progressBar.setValue(int(value))

    def captureComplete(self):

        self.captureButton.setDisabled(False)
        self.captureButton.setText("Capture")
        self.captureButton.setStyleSheet("")
        self.capturedImages.setDisabled(False)
        self.countLabel.setDisabled(False)
        self.numberOfFrames.setDisabled(False)
        self.delayLabel.setDisabled(False)
        self.delayTime.setDisabled(False)
        self.progressBar.setVisible(False)
        self.liveViewButton.setVisible(True)
        self.configPanel.setDisabled(False)


    def updateAcquisition(self, acquiring: bool):

        if acquiring:
            self.liveViewButton.setStyleSheet("background: brown; color: white;")
            self.liveViewButton.setText("Stop Continuous Acquisition")
        else:
            self.liveViewButton.setStyleSheet("")
            self.liveViewButton.setText("Start Continuous Acquisition")


    
    def live(self):

        if self.spectrometer.isAcquiring():
            self.spectrometer.stopAcquisition()
        else:
            self.spectrometer.startAcquisition()


    def drawSpectrum(self, spec: Spectrum):

        if self.bufferLock.locked():
            return

        self.spectrumSignal.emit(spec)
        Util.sleep(10)

        
    def doDraw(self, spec: Spectrum):

        with self.bufferLock:

            try:
                self.plotData.setData(spec.getWavelengths(), spec.getCounts())
            except:
                print("Exception when drawing spectrum")


    def saveToH5(self, spectra):

        try:
            file = df.current()
        except:
            self.errorMessage.showMessage("No HDF5 data file currently open to save to.")
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

            for spectrum in spectra:
                self.spectrumToDataset(group, spectrum, pattern, counter)
                counter += 1

        finally:

            file.flush()


    def spectrumToDataset(self, group: h5py.Group, spectrum: Spectrum, pattern: str, counter: int = 0) -> h5py.Dataset:
        
        name = pattern % counter

        while name in group:
            counter += 1
            name     = pattern % counter


        ds = group.create_dataset(name, data = np.array([np.array(spectrum.getWavelengths()), np.array(spectrum.getCounts())]))

        self.writeAttributes(ds, spectrum)

        return ds


    def writeAttributes(self, ds: h5py.HLObject, data: Union[Dict[str, object], Spectrum]):

        if isinstance(data, Spectrum):
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

        
class FastSpectrometerPreviewGUI(QWidget, Generic[S]):

    drawSignal = Signal(Spectrum)

    def __init__(self, spectrometer: S):

        super().__init__()
        self.setLayout(QVBoxLayout())

        plot = pg.plot(left="Counts", bottom="Wavelength [m]")
        data = plot.plotItem.plot([], [])

        def update(spectrum: Spectrum):
            data.setData(spectrum.getWavelengths(), spectrum.getCounts())

        self.drawSignal.connect(update)
        spectrometer.addSpectrumListener(self.drawSignal.emit)

        self.layout().addWidget(plot)
