# -*- coding: utf-8 -*-
"""Driver for the Thorlabs ELL6 two-position (in/out) Elliptec slider."""

from pyopenlab.instrument.stage.thorlabs_ello import ElloDevice
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty


class Ell6(ElloDevice):
    """Thorlabs ELL6 discrete-position slider (2 positions by default).

    Position is tracked locally as a step index rather than via pulse counts, advanced
    one slot at a time with forward/backward commands.

    Note:
        ``__init__`` passes literal ``device_index=0, debug=0`` to ``super().__init__``,
        discarding the values supplied by the caller. Left unfixed as it is a behavioral
        change beyond a surgical fix.
    """

    positions = 2

    def __init__(self, serial_device, device_index=0, debug=0):
        """Connect and home the slider.

        Args:
            serial_device: A ``BusDistributor`` or a serial port name (e.g. ``"COM5"``).
            device_index: Device bus address.
            debug: Debug verbosity passed to the base class.
        """
        super().__init__(serial_device, device_index=0, debug=0)
        self.home()

    def home(self):
        """Home the slider and reset the tracked position index to 0."""
        self.query_device('ho')
        self._position = 0

    def set_position(self, pos):
        """Step the slider to position index ``pos``.

        Args:
            pos: Target index; must satisfy ``0 <= pos < positions``.
        """
        assert 0 <= pos < self.positions

        while pos > self._position:
            self.move_forward()
        while pos < self._position:
            self.move_backward()

    def get_position(self):
        """Return the locally tracked position index."""
        return self._position

    position = NotifiedProperty(get_position, set_position)

    def get_qt_ui(self):
        """Return the Qt control widget for this slider."""
        return ELL6UI(self)

    def move_forward(self):
        """Advance one position and increment the tracked index."""
        self.query_device('fw')
        self._position += 1

    def move_backward(self):
        """Retreat one position and decrement the tracked index."""
        self.query_device('bw')
        self._position -= 1


class ELL6UI(QuickControlBox):
    """Qt control box exposing the ELL6 position spinbox."""

    def __init__(self, instr):
        super().__init__('ELL6')
        self.add_spinbox('position', vmin=0, vmax=1)
        self.auto_connect_by_name(controlled_object=instr)


if __name__ == '__main__':
    f = Ell6('COM6')
    f.show_gui(False)
