from typing import Generic, TypeVar

from jisa.devices import Instrument as JInst
import pyjisa.autoload
from qtpy.QtWidgets import QGroupBox
from qtpy.QtWidgets import QVBoxLayout

from pyopenlab.instrument import Instrument
from pyopenlab.ui.widgets.jisa import JISAConfigPanel

I = TypeVar("I", bound=JInst)


class JInstrument(Instrument, Generic[I]):

    def __init__(self, instrument: I):

        super().__init__()

        self._instrument = instrument

    def __getattr__(self, name):

        if hasattr(self._instrument, name):
            return getattr(self._instrument, name)
        else:
            raise AttributeError()

    def get_qt_ui(self):

        box = QGroupBox(self._instrument.getName())
        vbox = QVBoxLayout()
        box.setLayout(vbox)
        vbox.addWidget(JISAConfigPanel(self._instrument))

        return box
