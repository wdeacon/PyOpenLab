import os
from threading import Lock

from numpy import int32
import pyjisa.autoload
import pyqtgraph as pg

import numpy as np
from qtpy import uic
from qtpy.QtCore import QThreadPool, Qt, Signal
from qtpy.QtGui import QImage, QPainter, QPen, QPixmap
from qtpy.QtWidgets import *

from jisa                               import Util
from jisa.results                       import ResultTable, ResultList, Column
from jisa.devices.camera                import Camera
from jisa.devices.camera.frame          import Frame
from jisa.devices.spectrometer          import CameraSpectrometer
from jisa.devices.spectrometer.spectrum import Spectrum

from typing import TypeVar, Generic

from nplab.ui.widgets.jisa import JISAConfigPanel
from nplab.ui.widgets.jisa.widgets import ResultTableWidget

S = TypeVar("S", bound=CameraSpectrometer)
C = TypeVar("C", bound=Camera)

class CSConfigGUI(QWidget, Generic[S, C]):

    drawFrameSignal    = Signal(QPixmap)
    drawSpectrumSignal = Signal(Spectrum)

    def __init__(self, cs: S):

        super().__init__()

        self.spectrometer : S        = cs
        self.camera       : C        = cs.getCamera()
        self.buffer                  = None
        self.arr                     = None
        self.specBuffer   : Spectrum = None

        self.cameraImage     : QLabel
        self.spectrumBox     : QGroupBox
        self.configBox       : QGroupBox
        self.startX          : QSpinBox
        self.startY          : QSpinBox
        self.endX            : QSpinBox
        self.endY            : QSpinBox
        self.binning         : QSpinBox
        self.wavelengths     : QHBoxLayout
        self.showWavelengths : QPushButton
        self.addRow          : QPushButton
        self.remRow          : QPushButton
        self.closeButton     : QPushButton
        self.liveViewButton  : QPushButton
        self.applyButton     : QPushButton
        self.typeBox         : QComboBox
        self.fitOrder        : QSpinBox
        
        # Load UI from file
        uic.loadUi((os.path.dirname(__file__) + '/resources/csconfig.ui'), self)

        # Create other QT elements
        self.pool           = QThreadPool()
        self.errorMessage   = QErrorMessage()
        self.cameraLock     = Lock()
        self.cameraDrawLock = Lock()
        self.spectrumLock   = Lock()
        self.configPanel    = JISAConfigPanel(self.camera, self.prepareCamera, self.restoreCamera)
        self.plot           = pg.plot(left="Counts")
        self.plotData       = self.plot.plotItem.plot([], [])
        self.table          = ResultTableWidget()

        self.I = Column.ofIntegers("Channel Index")
        self.W = Column.ofDoubles("Wavelength", "m")
        data   = ResultList(self.I, self.W)

        self.table.setResultTable(data)

        self.wavelengths.addWidget(self.table)
        self.configBox.layout().addWidget(self.configPanel)
        self.spectrumBox.layout().addWidget(self.plot)

        self.camera.addFrameListener(self.frameListener)
        self.spectrometer.addSpectrumListener(self.spectrumListener)
        self.spectrometer.addAcquisitionListener(self.updateAcquisition)

        self.setupConnections()
        self.typeChange()


    def setupConnections(self):

        self.liveViewButton.clicked.connect(self.live)
        self.applyButton.clicked.connect(self.setConverter)
        self.typeBox.currentTextChanged.connect(self.typeChange)
        self.closeButton.clicked.connect(self.close)
        self.drawFrameSignal.connect(self.drawFrame)
        self.drawSpectrumSignal.connect(self.drawSpectrum)


    def typeChange(self):

        disabled = self.typeBox.currentText() == "Full Vertical Binning"

        self.startX.setDisabled(disabled)
        self.startY.setDisabled(disabled)
        self.endX.setDisabled(disabled)
        self.endY.setDisabled(disabled)
        self.binning.setDisabled(disabled)


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


    def prepareCamera(self, camera: C) -> bool:

        if camera.isAcquiring():
            camera.stopAcquisition()
            return True
        else:
            return False
        

    def restoreCamera(self, camera: C, result: bool):

        if result:
            camera.startAcquisition()


    def setConverter(self):

        if self.spectrometer.isAcquiring():
            self.spectrometer.stopAcquisition()
            stopped = True
        else:
            stopped = False

        wavelengths = {r.get(self.I): r.get(self.W) for r in self.table.getResultTable()}

        if self.typeBox.currentText() == "Full Vertical Binning":

            self.spectrometer.setConverterFullVerticalBinning(wavelengths, self.fitOrder.value())

        else:

            startX      = int32(self.startX.value())
            startY      = int32(self.startY.value())
            endX        = int32(self.endX.value())
            endY        = int32(self.endY.value())
            binning     = int32(self.binning.value())

            if len(wavelengths) < 2:
                wavelengths.clear()
                wavelengths[int32(0)] = 0.0
                wavelengths[int32(1)] = 1.0

            self.spectrometer.setConverter(startX, startY, endX, endY, binning, wavelengths)


        if stopped:
            self.spectrometer.startAcquisition()


    def frameListener(self, frame: Frame):

        try:

            # So that we don't have multiple threads trying to access the buffer at the same time
            with self.cameraLock:

                # If the frame size has changed, then we need to recreate the buffer, otherwise we should reuse it
                if self.buffer is None or len(self.buffer) != frame.size():
                    self.buffer = frame.getARGBData()
                    self.arr    = np.array(self.buffer)
                else:
                    frame.readARGBData(self.buffer)
                    np.copyto(self.arr, self.buffer)

                # Record dimensions incase we need to redraw before a new frame comes in
                self.lastWidth  = frame.getWidth()
                self.lastHeight = frame.getHeight()

                # Convert the buffer into a pixmap
                pixmap = QPixmap(QImage(self.arr, self.lastWidth, self.lastHeight, QImage.Format.Format_ARGB32))

                self.drawFrameSignal.emit(pixmap)

        except:
            print("Exception when drawing frame")
        finally:
            Util.sleep(100)


    def resizeEvent(self, a0):
        self.redrawFrame()
        return super().resizeEvent(a0)
    

    def redrawFrame(self):

        with self.cameraDrawLock:

            try:

                # If these haven't been set, then we can't possibly redraw, so give up
                if self.lastWidth is None or self.lastHeight is None:
                    return

                pixmap = QPixmap(QImage(self.arr, self.lastWidth, self.lastHeight, QImage.Format.Format_ARGB32))

                self.drawFrameSignal.emit(pixmap)

            except:
                print("Exception when trying to redraw frame")

        Util.sleep(10)


    def drawFrame(self, pixmap: QPixmap):

        try:
            self.cameraImage.setPixmap(pixmap.scaled(self.cameraImage.width(), self.cameraImage.height(), Qt.KeepAspectRatio))
        except Exception as e:
            print("Exception occurred when drawing frame. " + str(e))



    def spectrumListener(self, spec: Spectrum):

        # So that we don't have multiple threads trying to access the buffer at the same time
        with self.spectrumLock:

            if self.specBuffer is None or self.specBuffer.size() != spec.size():
                self.specBuffer = spec.copy()
            else:
                self.specBuffer.copyFrom(spec)

            self.drawSpectrumSignal.emit(self.specBuffer)

        Util.sleep(100)


    def drawSpectrum(self, spec: Spectrum):
            
        with self.spectrumLock:

            try:
                if self.showWavelengths.isChecked():
                    self.plotData.setData(spec.listWavelengths(), spec.listCounts())
                else:
                    self.plotData.setData(np.arange(spec.size()), spec.listCounts())

            except:
                print("Exception when drawing spectrum")
