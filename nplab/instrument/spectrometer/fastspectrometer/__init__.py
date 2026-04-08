import pyjisa.autoload
import pyqtgraph as pg
from qtpy.QtCore import Signal

from typing import Generic, List, Tuple, Callable, TypeVar
from jisa.devices.spectrometer import Spectrometer as JSpectrometer, Spectrograph as JSpectrograph
from jisa.devices.spectrometer.spectrum import Spectrum
from qtpy.QtWidgets import QVBoxLayout, QWidget

from nplab.instrument import Instrument
from nplab.instrument.spectrometer import Spectrometer
from nplab.instrument.spectrometer.fastspectrometer.gui import FastSpectrometerGUI, FastSpectrometerPreviewGUI

S = TypeVar("S", bound=JSpectrometer)

class FastSpectrometer(Instrument, Generic[S]):

    drawSignal = Signal(Spectrum)

    def __init__(self, spectrometer: S):

        super().__init__()

        self.spectrometer = spectrometer


    def getSpectrometer(self) -> S:
        return self.spectrometer
    

    def get_qt_ui(self, control_only=False, display_only=False):
        return FastSpectrometerGUI(self.spectrometer)
    
    def get_control_widget(self):
        return self.get_qt_ui()
    
    def get_preview_widget(self):
        return FastSpectrometerPreviewGUI(self.spectrometer)

        
