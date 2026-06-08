# -*- coding: utf-8 -*-
"""Driver for the Thorlabs ELL20 linear Elliptec translation stage.

Unlike the rotary ELLx models, the ELL20 measures travel in millimetres. Pulse scaling
therefore uses ``PULSES_PER_MM`` (pulses per mm) rather than pulses per revolution.
"""

import numpy as np

from pyopenlab.instrument.stage.thorlabs_ello import bytes_to_binary
from pyopenlab.instrument.stage.thorlabs_ello import ElloDevice
from pyopenlab.instrument.stage.thorlabs_ello import int_to_hex
from pyopenlab.instrument.stage.thorlabs_ello import int_to_twos_complement
from pyopenlab.instrument.stage.thorlabs_ello import twos_complement_to_int
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty


class Ell20(ElloDevice):
    """Thorlabs ELL20 linear translation stage (positions in millimetres).

    ``TRAVEL`` (mm) and ``PULSES_PER_MM`` are read from the device at construction.

    Note:
        ``__init__`` passes literal ``device_index=0, debug=0`` to ``super().__init__``,
        discarding the values supplied by the caller. Left unfixed as it is a behavioral
        change beyond a surgical fix.
    """

    def __init__(self, serial_device, device_index=0, debug=0):
        """Connect and read travel/pulse parameters from the device.

        Args:
            serial_device: A ``BusDistributor`` or a serial port name (e.g. ``"COM5"``).
            device_index: Device bus address.
            debug: Debug verbosity passed to the base class.
        """
        super().__init__(serial_device, device_index=0, debug=0)

        self.configuration = self.get_device_info()
        self.TRAVEL = self.configuration["travel"]
        self.PULSES_PER_MM = self.configuration["pulses"]
        if self.debug > 0:
            print("Travel (mm):", self.TRAVEL)
            print("Pulses per mm", self.PULSES_PER_MM)
            print("Device status:", self.get_device_status())

    def _position_to_pulse_count(self, position):
        """Convert a position in mm to a rounded motor pulse count.

        Used when building move commands sent to the stage.

        Args:
            position: Target position in millimetres.

        Returns:
            int: Nearest integer pulse count (``position * PULSES_PER_MM``).
        """
        pulses = int(np.rint(position * self.PULSES_PER_MM))
        if self.debug > 0:
            print("Input position:", position)
            print("Pulses:", pulses)
        return pulses

    def _pulse_count_to_position(self, pulse_count):
        """Convert a motor pulse count back to a position in mm.

        Inverse of ``_position_to_pulse_count``; used when decoding stage responses.

        Args:
            pulse_count: Signed pulse count reported by the stage.

        Returns:
            float: Position in millimetres.
        """
        return pulse_count / self.PULSES_PER_MM

    def _position_to_hex_pulses(self, position):
        """Encode a position (mm) as the hex pulse-count string the protocol expects.

        Args:
            position: Target position in millimetres.

        Returns:
            str: Hex string of a two's-complement pulse count.
        """

        # convert position to number of pulses used to drive motors:
        pulses_int = self._position_to_pulse_count(position)
        if self.debug > 0:
            print("Pulses (int)", pulses_int)
        # make two's complement to allow for -ve values
        pulses_int = int_to_twos_complement(pulses_int)
        if self.debug > 0:
            print("Pulses (int,2s compl)", pulses_int)
        # convert integer to hex
        pulses_hex = int_to_hex(pulses_int)
        if self.debug > 0:
            print("Pulses hex:", pulses_hex)
        return pulses_hex

    def _hex_pulses_to_position(self, hex_pulse_position):
        """Decode a hex pulse-count string from the stage into a position in mm.

        Args:
            hex_pulse_position: Hex string carrying a two's-complement pulse count.

        Returns:
            float: Position in millimetres.
        """
        binary_pulse_position = bytes_to_binary(hex_pulse_position)
        int_pulse_position = twos_complement_to_int(binary_pulse_position)
        return self._pulse_count_to_position(int_pulse_position)

    def move_absolute(self, position, blocking=True):
        """Move to an absolute position measured from the home position.

        Args:
            position: Target position in millimetres.
            blocking: If True, wait until motion stops before returning.

        Returns:
            dict: Decoded status/position reply.
        """

        pulses_hex = self._position_to_hex_pulses(position)
        response = self.query_device("ma{0}".format(pulses_hex))

        header = response[0:3]

        if blocking:
            self._block_until_stopped()
        return self._decode_position_response(response)

    def get_position(self, axis=None):
        """Query the stage and return its current position in mm.

        Overrides ``Stage.get_position``.

        Args:
            axis: Ignored; present for ``Stage`` interface compatibility.

        Returns:
            float: Current position in millimetres.

        Raises:
            ValueError: If the reply header is not a position (``PO``) response.
        """
        response = self.query_device("gp")
        header = response[0:3]
        if header == "{0}PO".format(self.device_index):
            # position given in twos complement representation
            byte_position = response[3:11]
            binary_position = bytes_to_binary(byte_position)
            pulse_position = twos_complement_to_int(binary_position)
            position = float(pulse_position) / self.PULSES_PER_MM
            return position
        else:
            raise ValueError("Incompatible Header received:{}".format(header))

    def move_home(self, blocking=True):
        """Move to the factory default home position.

        Resetting the home position (supported by the Thorlabs API) is intentionally not
        exposed here, as Thorlabs advises against it.

        Args:
            blocking: If True, wait until motion stops before returning.

        Returns:
            dict: Decoded status/position reply.
        """

        response = self.query_device("ho")
        if blocking:
            self._block_until_stopped()
        return self._decode_position_response(response)

    def get_qt_ui(self):
        """Return the Qt control widget for this stage."""
        return ELL20UI(self)


class ELL20UI(QuickControlBox):
    """Qt control box with a position spinbox spanning the stage's full travel."""

    def __init__(self, stage):
        super().__init__()
        self.add_doublespinbox('position', 0, stage.TRAVEL)
        self.auto_connect_by_name(controlled_object=stage)


class Ell20BiPositional(Ell20):
    """ELL20 used as a two-state device, snapping to fixed slots along its travel.

    ``SLOTS`` are fractions of ``TRAVEL`` and ``TOLERANCE`` is the fractional window
    within which the stage is considered to be at a slot.
    """

    SLOTS = (0.05, 0.95)  # fractions of travel
    TOLERANCE = 0.05

    def __init__(self, *args, **kwargs):
        """Initialize as an ELL20 and alias the pulse scaling for inherited helpers.

        Args:
            *args: Forwarded to ``Ell20.__init__``.
            **kwargs: Forwarded to ``Ell20.__init__``.
        """
        super().__init__(*args, **kwargs)
        # self.move_home()
        # self.slot = 0
        self.PULSES_PER_REVOLUTION = self.PULSES_PER_MM

    def get_slot(self):
        """Return the index of the slot the stage is currently at.

        Returns:
            int: Index into ``SLOTS`` if within ``TOLERANCE`` of a slot, else ``None``
            (a warning is logged when at no recognized position).
        """
        frac = self.get_position() / self.TRAVEL
        for i, slot in enumerate(self.SLOTS):
            if abs(frac - slot) < self.TOLERANCE:
                return i
        self.log('not in either position', level='warn')

    def set_slot(self, index):
        """Move to the slot at ``index``.

        Args:
            index: Index into ``SLOTS``.
        """
        self.move(self.SLOTS[index] * self.TRAVEL)

    slot = NotifiedProperty(get_slot, set_slot)

    def center(self):
        """Snap to whichever slot is closest to the current position."""
        slot = min(enumerate(self.SLOTS),
                   key=lambda i_s: abs(i_s[1] - (self.get_position() / self.TRAVEL)))[0]
        self.slot = slot

    def get_qt_ui(self):
        """Return the Qt control widget for the bi-positional stage."""
        return Ell20BiPositionalUi(self)


class Ell20BiPositionalUi(QuickControlBox):
    """Qt control box exposing the slot selector for a bi-positional ELL20."""

    def __init__(self, stage):
        super().__init__()

        self.add_spinbox('slot', 0, len(stage.SLOTS))
        self.auto_connect_by_name(controlled_object=stage)


if __name__ == "__main__":
    stage = Ell20BiPositional('COM6')
    # stage = Thorlabs_ELL20("COM10", debug=False)
    stage.show_gui(False)
