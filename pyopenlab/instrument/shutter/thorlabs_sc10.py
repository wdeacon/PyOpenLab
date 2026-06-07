"""Serial driver for the Thorlabs SC10 shutter controller."""

import pyopenlab.instrument.serial_instrument as serial
from pyopenlab.instrument.shutter import Shutter


def bool_to_state(Bool):
    """Convert a boolean open/closed flag to a state string.

    Args:
        Bool: ``True`` for open, ``False`` for closed.

    Returns:
        str: "Open" if ``Bool`` is truthy, otherwise "Closed".
    """
    if Bool:
        return 'Open'
    if not Bool:
        return 'Closed'


def state_to_bool(state):
    """Convert a state string to a boolean open/closed flag.

    Args:
        state: Either "Open" or "Closed".

    Returns:
        bool: ``True`` for "Open", ``False`` for "Closed".
    """
    if state == 'Open':
        return True
    if state == 'Closed':
        return False


class ThorLabsSC10(Shutter, serial.SerialInstrument):
    """Thorlabs SC10 shutter controller (serial).

    ``_state`` caches the shutter state in software because communication with
    this controller frequently fails: :meth:`toggle` always works, but
    ``query('ens?')`` often returns ``None`` along with "Command did not echo!!!".
    ``_state`` may be wrong initially if the shutter is open and communication
    fails; in that case set it manually, e.g.::

        shutter._state = 'Open'

    ``_state`` is overwritten whenever communication succeeds, maximising the
    chance of it being correct. Using the physical buttons on the unit will
    desynchronise it. (-ee306)
    """

    port_settings = dict(
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  # wait at most one second for a response
        writeTimeout=1,  # similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    termination_character = "\r"  #: All messages to or from the instrument end with this character.

    def __init__(self, port=None):
        """Open the serial connection and read back the initial state.

        Args:
            port: The serial port the controller is connected to (e.g. "COM7").
        """
        serial.SerialInstrument.__init__(self, port=port)
        Shutter.__init__(self)
        self.ignore_echo = True
        self._state = 'Closed'  # usually the case
        self.get_state(report_success=True)  # overwrites self._state if communication succeeds

    def toggle(self):
        """Toggle the shutter by sending ``ens`` and flipping the cached state."""
        self.write('ens')
        self._state = bool_to_state(not state_to_bool(self._state))  #toggles self._state

    def get_state(self, report_success=False):
        """Query the controller for the shutter state, caching it in ``_state``.

        Args:
            report_success: If ``True``, print a warning when communication
                fails and the cached state is returned instead.

        Returns:
            str: "Open" or "Closed". On communication failure, the last cached
            ``_state`` value is returned.
        """
        try:
            state = bool(int(self.query('ens?')))

            if state:
                self._state = 'Open'
                return self._state
            if not state:
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
        """Set the shutter, toggling only if it differs from the current state.

        Args:
            state: The desired state, "Open" or "Closed".
        """
        if state_to_bool(self.get_state()) != state_to_bool(state):
            self.toggle()

    def open_shutter(self):
        """Open the shutter if it is not already open."""
        if not state_to_bool(self.get_state()):
            self.toggle()
        elif state_to_bool(self._state):
            print('Shutter is already open!')

    def close_shutter(self):
        """Close the shutter if it is not already closed."""
        if state_to_bool(self._state):
            self.toggle()
        elif not state_to_bool(self._state):
            print('Shutter is already closed!')

    def set_mode(self, n):
        """Set the operating mode of the controller.

        Args:
            n: The mode number, where:

                * 1: Manual Mode
                * 2: Auto Mode
                * 3: Single Mode
                * 4: Repeat Mode
                * 5: External Gate Mode
        """
        self.query('mode=' + str(n))

    def get_mode(self):
        """Query the controller for the current operating mode.

        Note:
            This queries ``mode?`` but discards the result without returning it,
            so it currently has no observable effect. Left unchanged to avoid a
            behaviour change.
        """
        self.query('mode?')


if __name__ == '__main__':
    #    import sys
    #    from pyopenlab.utils.gui import *
    #    app = get_qt_app()

    # shutter = ThorLabsSC10('22d868e8-6908-11ee-a762-d08e791254b7')
    shutter = ThorLabsSC10('COM7')

    # shutter.query('ens?', termination_line = "r")
    #     ui = shutter.get_qt_ui()
    #    ui.show()
    #    sys.exit(app.exec_())
    shutter.show_gui()
