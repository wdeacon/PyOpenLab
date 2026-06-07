"""Serial driver for the Thorlabs SHB05BT shutter, controlled via the RTS line."""

import serial

from pyopenlab.instrument.shutter import Shutter


# Reverse logic: the RTS line is asserted (True) when the shutter is CLOSED.
def bool_to_state(Bool):
    """Convert an RTS line value to a shutter state string (reverse logic).

    Args:
        Bool: The RTS line value; ``True`` means closed.

    Returns:
        str: "Open" if ``Bool`` is falsy, otherwise "Closed".
    """
    if not Bool:
        return 'Open'
    if Bool:
        return 'Closed'


def state_to_bool(state):
    """Convert a shutter state string to an RTS line value (reverse logic).

    Args:
        state: Either "Open" or "Closed".

    Returns:
        bool: ``False`` for "Open", ``True`` for "Closed".
    """
    if state == 'Open':
        return False
    if state == 'Closed':
        return True


class ThorLabsSHB05BT(Shutter):
    """Thorlabs SHB05BT shutter driven directly through the serial RTS line.

    Asserting RTS (``True``) closes the shutter; de-asserting it opens it.
    """

    def __init__(self, port=None):
        """Open the serial port and read back the initial state.

        Args:
            port: The serial port the shutter is connected to (e.g. "COM4").
        """
        self.ser = serial.Serial(port=port)
        Shutter.__init__(self)
        self.ignore_echo = True
        self.state = 'Closed'  # usually the case
        self.get_state(report_success=True)  # overwrites self._state if communication succeeds

    def get_state(self, report_success=False):
        """Read the shutter state from the RTS line, caching it in ``_state``.

        Args:
            report_success: If ``True``, print a warning when reading fails and
                the cached state is returned instead.

        Returns:
            str: "Open" or "Closed". On failure, the cached ``_state`` is
            returned.
        """
        try:
            state = self.ser.rts

            if not state:
                self._state = 'Open'
                return self._state
            if state:
                self._state = 'Closed'
                return self._state
            assert False
        except (ValueError, AssertionError):
            if report_success:
                print(
                    '''Communication with shutter failed; assuming shutter is closed.\nChange shutter._state if not!'''
                )
            return self._state

    def set_state(self, state):
        """Set the shutter state by driving the RTS line.

        Args:
            state: The desired state, "Open" or "Closed".
        """
        self.ser.rts = state_to_bool(state)
        self._state = state

    def open_shutter(self):
        """Open the shutter."""
        self.set_state("Open")

    def close_shutter(self):
        """Close the shutter."""
        self.set_state("Closed")

    def toggle(self):
        """Toggle the shutter by inverting the RTS line."""
        self.ser.rts = not self.ser.rts
        self._state = bool_to_state(self.ser.rts)


if __name__ == '__main__':
    #    import sys
    #    from pyopenlab.utils.gui import *
    #    app = get_qt_app()

    shutter = ThorLabsSHB05BT('COM4')
    # shutter.query('ens?', termination_line = "r")
    #     ui = shutter.get_qt_ui()
    #    ui.show()
    #    sys.exit(app.exec_())
    shutter.show_gui()
