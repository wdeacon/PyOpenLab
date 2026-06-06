# -*- coding: utf-8 -*-
"""Drivers for Thorlabs ELL-series filter/flipper holders on an ELLB serial bus."""
from pyopenlab.instrument import Instrument
from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty


def bytes_to_binary(bytearr, debug=0):
    """Convert an iterable of hex-string bytes to a binary-string representation.

    Args:
        bytearr: Iterable of hexadecimal byte strings (base 16).
        debug: If greater than 0, print intermediate values.

    Returns:
        The concatenated binary representation as a string.
    """
    if debug > 0:
        print(bytearr)
    bytes_as_binary = [format(int(b, base=16), "#06b").replace("0b", "") for b in bytearr]
    if debug > 0:
        print(bytes_as_binary)
    binary = "".join(bytes_as_binary)
    return binary


def twos_complement_to_int(binary, debug=0):
    """Decode a two's-complement binary string to a signed value.

    Args:
        binary: Binary string whose leading bit is the sign bit.
        debug: If greater than 0, print the input.

    Returns:
        The signed value as a float.
    """
    if debug > 0:
        print(binary)
    N = len(binary)
    a_N = int(binary[0])
    return float(-a_N * 2**(N - 1) + int(binary[1:], base=2))


def int_to_hex(integer, padded_length=8, debug=0):
    """Convert an integer to an upper-case, zero-padded hex string (no ``0x``).

    Args:
        integer: The integer to convert.
        padded_length: Minimum number of hex digits; the result is left-padded
            with zeros to this width.
        debug: Unused; accepted for signature parity with the other helpers.

    Returns:
        The hexadecimal representation as an upper-case string.
    """
    outp = (format(integer, "#0{}x".format(padded_length + 2)).replace("0x", "")).upper()
    return outp


def int_to_twos_complement(integer, padded_length=16, debug=0):
    """Encode a signed integer as its two's-complement integer value.

    Args:
        integer: Signed integer to encode. Non-negative values are returned
            unchanged; negative values are converted to two's complement.
        padded_length: Bit width used when building the binary representation.
        debug: If greater than 0, print intermediate values.

    Returns:
        For non-negative input, ``integer`` itself; for negative input, the integer
        value of its two's-complement bit pattern.
    """
    #number is above 0 - return binary representation:
    if integer >= 0:
        return integer

    #number is below zero - return twos complement representation:
    elif integer < 0:
        if debug > 0:
            print("Below zero - returning twos complement")
        integer = -1 * integer
        binary = format(integer, "0{}b".format(padded_length + 2)).replace("0b", "")
        ones_complement = [str(1 - int(b)) for b in str(binary)]
        ones_complement = int("".join(ones_complement))
        twos_complement = int("0b" + str(ones_complement), base=2) + 1
        twos_complement = format(twos_complement, "034b").replace("0b", "")
        if debug > 0:
            print("input:", integer)
            print("binary:", binary)
            print("ones comp:", ones_complement)
            print("twos comp (int):", int(twos_complement, base=2))
        return int("0b" + twos_complement, base=2)


class BusDistributor(SerialInstrument):
    """Serial port wrapper for a Thorlabs ELLB distributor bus.

    Each bus can host several devices, which are assigned distinct device indices
    by the Thorlabs Ello software; without that they all default to index 0 and
    cannot be addressed separately.
    """

    def __init__(self, port):
        self.termination_character = '\n'
        self.port_settings = dict(baudrate=9600,
                                  bytesize=8,
                                  stopbits=1,
                                  parity='N',
                                  timeout=2,
                                  writeTimeout=2,
                                  xonxoff=False)
        super().__init__(port)


class ThorlabsELL6(Instrument):
    """Driver for the Thorlabs ELL6 two-position filter slider."""

    #default id is 0, but if multiple devices of same type connected may have others
    VALID_DEVICE_IDs = [str(v) for v in list(range(11)) + ["A", "B", "C", "D", "E", "F"]]

    #How much a stage sleeps (in seconds) between successive calls to .get_position.
    #Used to make blocking calls to move_absolute and move_relative.
    BLOCK_SLEEPING_TIME = 0.02
    #Theshold for position accuracy when stage is meant to be stationary
    #If difference between successive calls to get_position returns value
    #whose difference is less than jitter - consider stage to have stopped
    POSITION_JITTER_THRESHOLD = 0.02

    #human readable status codes
    DEVICE_STATUS_CODES = {
        0: "OK, no error",
        1: "Communication Timeout",
        2: "Mechanical time out",
        3: "Command error or not supported",
        4: "Value out of range",
        5: "Module isolated",
        6: "Module out of isolation",
        7: "Initialization error",
        8: "Thermal error",
        9: "Busy",
        10: "Sensor Error",
        11: "Motor Error",
        12: "Out of Range",
        13: "Over current error",
        14: "OK, no error",
        "OutOfBounds": "Reserved"}
    positions = 2

    def __init__(self, serial_device, device_index=0, debug=0):
        """Initialise the holder and home it.

        Args:
            serial_device: Either a :class:`BusDistributor` instance or a serial
                port name (e.g. ``"COM5"``), in which case a bus is created for it.
            device_index: Device index on the ELLB bus (must be in
                :attr:`VALID_DEVICE_IDs`).
            debug: If greater than 0, print raw queries and responses.

        Raises:
            ValueError: If ``device_index`` is not a valid ELLB device id.
        """
        super().__init__()
        if type(serial_device) is str:
            self.serial_device = BusDistributor(serial_device)
        else:
            self.serial_device = serial_device
        self.debug = debug

        if str(device_index) not in self.VALID_DEVICE_IDs:
            raise ValueError("Device ID: {} is not valid!".format(device_index))
        self.device_index = device_index
        self.home()

    def home(self):
        """Home the device and reset the tracked position to 0."""
        self.query_device('ho')
        self._position = 0

    def set_position(self, pos):
        """Step the holder to an absolute slot.

        Args:
            pos: Target slot index; must satisfy ``0 <= pos < positions``.
        """
        assert 0 <= pos < self.positions

        while pos > self._position:
            self.move_forward()
        while pos < self._position:
            self.move_backward()

    def get_position(self):
        """Return the current slot index."""
        return self._position

    position = NotifiedProperty(get_position, set_position)

    def query_device(self, query):
        """Send a query prefixed with this device's bus index.

        Args:
            query: The device command (without the leading device index).

        Returns:
            The raw response string from the serial device.
        """
        raw_query = "{0}{1}".format(self.device_index, query)
        if self.debug > 0:
            print("raw_query", raw_query)
        raw_response = self.serial_device.query(raw_query)
        if self.debug > 0:
            print("raw_response", raw_response)
        return raw_response

    def get_qt_ui(self):
        """Return the Qt control widget for this ELL6 holder."""
        return ELL6UI(self)

    def move_forward(self):
        """Advance one slot and increment the tracked position."""
        self.query_device('fw')
        self._position += 1

    def move_backward(self):
        """Retreat one slot and decrement the tracked position."""
        self.query_device('bw')
        self._position -= 1


class ThorlabsELL9(ThorlabsELL6):
    """Driver for the Thorlabs ELL9 four-position filter slider."""

    positions = 4

    def get_qt_ui(self):
        """Return the Qt control widget for this ELL9 holder."""
        return ELL9UI(self)


class ELL6UI(QuickControlBox):
    """Qt control box with a 0-1 position spin box for an ELL6 holder."""

    def __init__(self, instr):
        super().__init__('ELL6')
        self.add_spinbox('position', vmin=0, vmax=1)
        self.auto_connect_by_name(controlled_object=instr)


class ELL9UI(QuickControlBox):
    """Qt control box with a 0-3 position spin box for an ELL9 holder."""

    def __init__(self, instr):
        super().__init__('ELL9')
        self.add_spinbox('position', vmin=0, vmax=3)
        self.auto_connect_by_name(controlled_object=instr)


if __name__ == '__main__':
    # f = ThorlabsELL6('COM9')
    f = ThorlabsELL9('COM6')
    f.show_gui(False)
