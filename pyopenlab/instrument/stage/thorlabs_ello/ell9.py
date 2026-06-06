"""Driver for the Thorlabs ELL9 four-position Elliptec slider."""

from pyopenlab.instrument.stage.thorlabs_ello.ell6 import Ell6
from pyopenlab.ui.ui_tools import QuickControlBox


class Ell9(Ell6):
    """Thorlabs ELL9 slider; an ``Ell6`` with four discrete positions."""

    positions = 4

    def get_qt_ui(self):
        """Return the Qt control widget for this slider."""
        return ELL9UI(self)


class ELL6UI(QuickControlBox):
    """Qt control box with an ELL6-range position spinbox (unused by ``Ell9``)."""

    def __init__(self, instr):
        super().__init__('ELL6')
        self.add_spinbox('position', vmin=0, vmax=1)
        self.auto_connect_by_name(controlled_object=instr)


class ELL9UI(QuickControlBox):
    """Qt control box exposing the ELL9 four-position spinbox."""

    def __init__(self, instr):
        super().__init__('ELL9')
        self.add_spinbox('position', vmin=0, vmax=3)
        self.auto_connect_by_name(controlled_object=instr)
