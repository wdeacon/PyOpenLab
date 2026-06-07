# -*- coding: utf-8 -*-
"""Serial drivers for Arduino-controlled TTL shutters.

Provides :class:`Arduino_TTL_shutter`, a single-channel shutter, and
:class:`Arduino_tri_shutter`, a multi-channel controller for two shutters and a
flip mirror, together with a small Qt control widget for the latter.
"""
from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.shutter import Shutter
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty


class Arduino_TTL_shutter(SerialInstrument, Shutter):
    """A serial-controlled single-channel Arduino TTL shutter."""

    def __init__(self, port=None):
        """Open the serial connection to the Arduino shutter.

        Args:
            port: The port the device is connected to, in any of the accepted
                serial formats (e.g. an int or a string such as "COM4").
        """
        self.termination_character = '\n'
        self.port_settings = {
            'baudrate': 9600,
            #       'bytesize':serial.EIGHTBITS,
            'timeout': 2,  #wait at most one second for a response
        }
        self.termination_character = '\n'
        SerialInstrument.__init__(self, port=port)
        Shutter.__init__(self)

    def get_state(self):
        """Query the Arduino for the shutter state.

        Returns:
            str: The device's response to the ``Read`` command.
        """
        return self.query('Read')

    def set_state(self, state):
        """Send a state command to the Arduino.

        Args:
            state: The command/state string to send to the device.
        """
        self.query(state)


class Arduino_tri_shutter(SerialInstrument):
    """Serial controller for two shutters and a flip mirror on one Arduino."""

    def __init__(self, port=None):
        """Open the serial connection to the tri-shutter Arduino.

        Args:
            port: The port the device is connected to, in any of the accepted
                serial formats (e.g. an int or a string such as "COM4").
        """
        self.termination_character = '\n'
        self.port_settings = {
            'baudrate': 9600,
            #       'bytesize':serial.EIGHTBITS,
            'timeout': 2,  #wait at most one second for a response
        }
        self.termination_character = '\r\n'
        SerialInstrument.__init__(self, port=port)

    def set_shutter_1_state(self, state):
        """Open or close shutter 1 (setter used by the GUI checkbox).

        Args:
            state: ``True`` to open shutter 1, ``False`` to close it.
        """
        if state == True:
            self._open_shutter_1()
        elif state == False:
            self._close_shutter_1()

    def set_shutter_2_state(self, state):
        """Open or close shutter 2 (setter used by the GUI checkbox).

        Args:
            state: ``True`` to open shutter 2, ``False`` to close it.
        """
        if state == True:
            self._open_shutter_2()
        elif state == False:
            self._close_shutter_2()

    def set_mirror_1_state(self, state):
        """Flip mirror 1 (setter used by the GUI checkbox).

        Args:
            state: ``True`` selects position 0, ``False`` selects position 1.
        """
        if state == True:
            self._flip_mirror_0()
        elif state == False:
            self._flip_mirror_1()

    def open_shutter_1(self):
        """Usable open shutter 1 function that updates GUI when used"""
        self.Shutter_1_State = True

    def close_shutter_1(self):
        """Usable close shutter 1 function that updates GUI when used"""
        self.Shutter_1_State = False

    def open_shutter_2(self):
        """Usable open shutter 2 function that updates GUI when used"""
        self.Shutter_2_State = True

    def close_shutter_2(self):
        """Usable close shutter 2 function that updates GUI when used"""
        self.Shutter_2_State = False

    def flip_mirror_0(self):
        """Flip the mirror to position 0, updating the GUI.

        Note:
            This sets ``Flipper_1_State`` to ``False``, identical to
            :meth:`flip_mirror_1`. It looks like a copy-paste bug (this method
            probably ought to set ``True``), but the correct value is ambiguous,
            so it is left unchanged.
        """
        self.Flipper_1_State = False

    def flip_mirror_1(self):
        """Flip the mirror to position 1, updating the GUI."""
        self.Flipper_1_State = False

    def _open_shutter_1(self):
        """do not use! Hidden access to open shutter """
        self.query('A')

    def _close_shutter_1(self):
        """do not use! hidden close shutter function"""
        self.query('B')

    def _open_shutter_2(self):
        """do not use! Hidden access to open shutter """
        self.query('C')

    def _close_shutter_2(self):
        """do not use! hidden close shutter function"""
        self.query('D')

    def _flip_mirror_0(self):
        """do not use! hidden open flipper function"""
        self.query('E')

    def _flip_mirror_1(self):
        """do not use! hidden open flipper function"""
        self.query('F')


#   def get_state(self):
#       return self.query('Read')
#   def set_state(self,state):
#       self.query(state)

    def get_qt_ui(self):
        """Return the Qt control widget for this tri-shutter.

        Returns:
            tri_shutter_ui: The control widget, also stored on ``self.ui``.
        """
        self.ui = tri_shutter_ui(self)
        return self.ui

    def read_state(self):
        """Query the Arduino for the state of all three channels.

        Returns:
            list[bool]: The states of shutter 1, shutter 2 and the flip mirror,
            parsed from the device's comma-separated response to ``S``.
        """
        states = self.query('S')
        states = states.split(',')
        states = [bool(int(state)) for state in states]
        return states

    states = NotifiedProperty(fget=read_state)

    def get_state_1(self):
        """Return the state of shutter 1.

        Returns:
            bool: ``True`` if shutter 1 is open.
        """
        return self.states[0]

    def get_state_2(self):
        """Return the state of shutter 2.

        Returns:
            bool: ``True`` if shutter 2 is open.
        """
        return self.states[1]

    def get_state_3(self):
        """Return the state of the flip mirror.

        Returns:
            bool: The flip mirror channel state.
        """
        return self.states[2]

    Shutter_1_State = NotifiedProperty(fset=set_shutter_1_state, fget=get_state_1)
    Shutter_2_State = NotifiedProperty(fset=set_shutter_2_state, fget=get_state_2)
    Flipper_1_State = NotifiedProperty(fset=set_mirror_1_state, fget=get_state_3)

    #      self.get_state()


class tri_shutter_ui(QuickControlBox):
    """Control widget exposing checkboxes for the two shutters and flip mirror."""

    def __init__(self, shutter):
        """Build the tri-shutter control widget.

        Args:
            shutter: The :class:`Arduino_tri_shutter` instance to control.
        """
        super(tri_shutter_ui, self).__init__(title='Tri_shutter')
        self.shutter = shutter
        self.add_checkbox('Shutter_1_State')
        self.add_checkbox('Shutter_2_State')
        self.add_checkbox('Flipper_1_State')
        self.auto_connect_by_name(controlled_object=self.shutter)


if __name__ == '__main__':
    shutter = Arduino_tri_shutter(port='COM4')
