# -*- coding: utf-8 -*-
"""Shared base classes and protocol helpers for Thorlabs ELLx (Elliptec) stages.

The Elliptec stages communicate over a shared serial bus. ``BusDistributor`` owns the
serial port; ``ElloDevice`` is the per-device base class. Each device is addressed by a
single hex digit (0-F) prefixed to every command, so several devices can share one bus.

Positions are exchanged on the wire as fixed-width hex strings encoding a signed pulse
count in two's complement. The conversion between physical units and pulses uses two
device parameters reported by ``get_device_info``:

    TRAVEL: full range of travel, in degrees (rotators) or mm (linear stages).
    PULSES: pulse count spanning the full travel.

``PULSES / TRAVEL`` therefore gives pulses per degree (or per mm).
"""
from functools import wraps
import time

import numpy as np

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.stage import Stage


def bytes_to_binary(bytearr, debug=0):
    """Convert a sequence of hex characters into its binary string representation.

    Args:
        bytearr: Iterable of hex characters (e.g. the per-byte slices of a hex response).
        debug: If greater than 0, print intermediate values.

    Returns:
        str: Concatenated binary string, 4 bits per input hex character.
    """
    if debug > 0:
        print(bytearr)
    bytes_as_binary = [format(int(b, base=16), "#06b").replace("0b", "") for b in bytearr]
    if debug > 0:
        print(bytes_as_binary)
    binary = "".join(bytes_as_binary)
    return binary


def twos_complement_to_int(binary, debug=0):
    """Decode a two's-complement binary string into a signed value.

    Args:
        binary: Binary string whose first bit is the sign bit.
        debug: If greater than 0, print the input.

    Returns:
        float: The signed integer value represented by the two's-complement string.
    """
    if debug > 0:
        print(binary)
    N = len(binary)
    a_N = int(binary[0])
    return float(-a_N * 2**(N - 1) + int(binary[1:], base=2))


def int_to_hex(integer, padded_length=8, debug=0):
    """Convert an integer to an uppercase, zero-padded hex string (no ``0x`` prefix).

    Args:
        integer: Value to convert.
        padded_length: Minimum number of hex digits; the result is left-padded with
            zeros to this width.
        debug: Unused; accepted for signature symmetry with the other helpers.

    Returns:
        str: Uppercase hex string of at least ``padded_length`` characters.
    """
    outp = (format(integer, "#0{}x".format(padded_length + 2)).replace("0x", "")).upper()
    return outp


def int_to_twos_complement(integer, padded_length=16, debug=0):
    """Return a non-negative integer encoding the two's complement of ``integer``.

    Non-negative inputs are returned unchanged. Negative inputs are converted to the
    two's-complement bit pattern (computed over ``padded_length`` bits) and returned as
    the unsigned integer value of that bit pattern, ready for hex encoding.

    Args:
        integer: Signed value to encode.
        padded_length: Bit width used to compute the complement.
        debug: If greater than 0, print intermediate values.

    Returns:
        int: ``integer`` itself when non-negative, otherwise the unsigned value of its
        two's-complement bit pattern.
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

    A single bus can host several Elliptec devices. Each device must be assigned a
    distinct address (device index) using the Thorlabs Ello software; otherwise they all
    default to address 0 and cannot be controlled independently.
    """

    def __init__(self, port):
        """Configure the bus serial port (9600 8N1) and open it.

        Args:
            port: Serial port name (e.g. ``"COM5"``).
        """
        self.termination_character = '\n'
        self.port_settings = dict(baudrate=9600,
                                  bytesize=8,
                                  stopbits=1,
                                  parity='N',
                                  timeout=2,
                                  writeTimeout=2,
                                  xonxoff=False)
        super().__init__(port)


def flushed(f):
    """Decorator that flushes the serial input buffer before and after the call.

    Stale bytes left on the shared bus from a previous device's reply would otherwise
    corrupt this device's response, so the buffer is cleared on both sides of ``f``.
    """

    @wraps(f)
    def inner(self, *args, **kwargs):
        self.serial_device.flush_input_buffer()
        retval = f(self, *args, **kwargs)
        self.serial_device.flush_input_buffer()
        return retval

    return inner


class ElloDevice(Stage):
    """Base class for a single Elliptec device on a shared bus.

    Subclasses (one per model) supply the device-specific ``TRAVEL`` and pulse-count
    parameters and override position handling as needed. Every command is prefixed with
    the device address so multiple devices can coexist on one ``BusDistributor``.

    Note:
        ``get_device_status`` references an undefined name ``Thorlabs_ELL8K`` and will
        raise ``NameError`` if called. It is left unfixed here as the fix is beyond a
        surgical change; ``DEVICE_STATUS_CODES`` on this class holds the same table it
        intends to use.
    """

    # default id is 0, but if multiple devices of same type connected may have others
    VALID_DEVICE_IDs = [str(v) for v in list(range(0, 11)) + ["A", "B", "C", "D", "E", "F"]]

    # How much a stage sleeps (in seconds) between successive calls to .get_position.
    # Used to make blocking calls to move_absolute and move_relative.
    BLOCK_SLEEPING_TIME = 0.1
    # Theshold for position accuracy when stage is meant to be stationary
    # If difference between successive calls to get_position returns value
    # whose difference is less than jitter - consider stage to have stopped
    POSITION_JITTER_THRESHOLD = 0.02
    BLOCK_TIMEOUT = 4.
    # human readable status codes
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

    def __init__(self, serial_device, device_index=0, debug=0):
        """Attach to a bus and select a device address.

        Args:
            serial_device: Either a serial port name (e.g. ``"COM5"``) to open a new
                bus, or an existing ``BusDistributor`` to share an open bus.
            device_index: Device address on the bus; must be one of ``VALID_DEVICE_IDs``.
            debug: If greater than 0, print raw queries/responses for troubleshooting.

        Raises:
            TypeError: If ``serial_device`` is neither a string nor a ``BusDistributor``.
            ValueError: If ``device_index`` is not a valid bus address.
        """
        if type(serial_device) is str:
            self.serial_device = BusDistributor(serial_device)
        elif isinstance(serial_device, BusDistributor):
            self.serial_device = serial_device
        else:
            raise TypeError('ello device is wrong type')
        self.debug = debug
        if str(device_index) not in self.VALID_DEVICE_IDs:
            raise ValueError("Device ID: {} is not valid!".format(device_index))
        self.device_index = device_index
        Stage.__init__(self)
        self.ui = None
        # self.configuration = self.get_device_info()

    @flushed
    def query_device(self, query):
        """Send a command prefixed with this device's address and return the reply.

        Args:
            query: Bare protocol command (e.g. ``"gp"``), without the address prefix.

        Returns:
            The raw response string from the device.
        """
        raw_query = "{0}{1}".format(self.device_index, query)
        if self.debug > 0:
            print("raw_query", raw_query)
        raw_response = self.serial_device.query(raw_query)
        if self.debug > 0:
            print("raw_response", raw_response)
        return raw_response

    def _angle_to_pulse_count(self, angle):
        """Convert an angle in degrees to a rounded motor pulse count.

        Uses ``PULSES_PER_REVOLUTION / TRAVEL`` as pulses per degree. Used when building
        move commands sent to the stage.

        Args:
            angle: Target angle in degrees.

        Returns:
            int: Nearest integer pulse count.
        """
        pulse_per_deg = self.PULSES_PER_REVOLUTION / float(self.TRAVEL)
        pulses = int(np.rint(angle * pulse_per_deg))
        if self.debug > 0:
            print("Input angle:", angle)
            print("Pulses:", pulses)
        return pulses

    def _pulse_count_to_angle(self, pulse_count):
        """Convert a motor pulse count back to an angle in degrees.

        Inverse of ``_angle_to_pulse_count``; used when decoding stage responses.

        Args:
            pulse_count: Signed pulse count reported by the stage.

        Returns:
            float: Angle in degrees.
        """
        return float(self.TRAVEL) * pulse_count / self.PULSES_PER_REVOLUTION

    def _angle_to_hex_pulses(self, angle):
        """Encode an angle as the hex pulse-count string the stage protocol expects.

        Args:
            angle: Angle in degrees, within ``[-360, 360]`` (the bounds themselves
                are accepted).

        Returns:
            str: Hex string of a two's-complement pulse count.

        Raises:
            ValueError: If ``angle`` is less than -360 or greater than 360.
        """
        if angle < -360.0 or angle > 360.0:
            raise ValueError("Valid angle bounds are: (-360,360) [exclusive]")

        # convert angle to number of pulses used to drive motors:
        pulses_int = self._angle_to_pulse_count(angle)
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

    def _hex_pulses_to_angle(self, hex_pulse_position):
        """Decode a hex pulse-count string from the stage into an angle in degrees.

        Args:
            hex_pulse_position: Hex string carrying a two's-complement pulse count.

        Returns:
            float: Angle in degrees.
        """
        binary_pulse_position = bytes_to_binary(hex_pulse_position)
        int_pulse_position = twos_complement_to_int(binary_pulse_position)
        return self._pulse_count_to_angle(int_pulse_position)

    def _decode_position_response(self, response):
        """Decode a status or position reply from a move/home command.

        Args:
            response: Raw reply to ``move_absolute``, ``move_relative`` or ``move_home``.

        Returns:
            dict: ``{"header", "status"}`` for a ``GS`` (status) reply, or
            ``{"header", "position"}`` for a ``PO`` (position) reply. ``None`` if the
            header matches neither.
        """
        header = response[0:3]
        if header == "{0}GS".format(self.device_index):
            # still moving
            status_code = int(response[3:5], base=16)
            status = self.DEVICE_STATUS_CODES[status_code]
            outp = {"header": header, "status": status}
            return outp
        elif header == "{0}PO".format(self.device_index):
            hex_pulse_position = response[3:11]
            position = self._hex_pulses_to_angle(hex_pulse_position)
            outp = {"header": header, "position": position}
            return outp

    def _block_until_stopped(self):
        """Poll position until it stops changing or ``BLOCK_TIMEOUT`` elapses.

        Successive ``position`` reads differing by less than ``POSITION_JITTER_THRESHOLD``
        are treated as the stage having stopped. Used to make moves blocking.
        """
        # stopped = False
        previous_angle = np.inf
        # current_angle = 1.0

        start = time.time()

        while time.time() - start < self.BLOCK_TIMEOUT:
            try:
                current_angle = self.position
            except ValueError:
                continue
            if (np.absolute(current_angle - previous_angle) < self.POSITION_JITTER_THRESHOLD):
                break
            time.sleep(self.BLOCK_SLEEPING_TIME)
            previous_angle = current_angle

    def get_position(self, axis=None):
        """Return the current position; must be implemented by a model subclass.

        Raises:
            NotImplementedError: Always, on the base class.
        """
        raise NotImplementedError('must subclass')
        # '''
        # Query stage for its current position, in degrees
        # This method overrides the Stage class' method
        # '''
        # response = self.query_device("gp")
        # header = response[0:3]
        # if header == "{0}PO".format(self.device_index):
        #     # position given in twos complement representation
        #     byte_position = response[3:11]
        #     binary_position = bytes_to_binary(byte_position)
        #     pulse_position = twos_complement_to_int(binary_position)
        #     degrees_position = self.TRAVEL * \
        #         (float(pulse_position)/self.PULSES_PER_REVOLUTION)
        #     return degrees_position
        # else:
        #     raise ValueError("Incompatible Header received:{}".format(header))

    def move(self, pos, axis=None, relative=False):
        """Move the stage (overrides ``Stage.move``).

        Args:
            pos: Target, in degrees within ``(-360, 360)`` for rotary stages.
            axis: Ignored; present for ``Stage`` interface compatibility.
            relative: If True, move relative to the current position, else absolute.
        """
        if relative:
            self.move_relative(pos)
        else:
            self.move_absolute(pos)

    def get_device_info(self):
        """Query the device identity and motion parameters.

        Subclasses call this at construction to populate ``TRAVEL`` and the pulse-count
        scaling. ``TRAVEL`` is the full range (deg or mm by model) and ``pulses`` is the
        pulse count spanning it, so ``pulses / TRAVEL`` is pulses per unit.

        Returns:
            dict: Keys ``header``, ``ell``, ``sn``, ``year``, ``firmware_release``,
            ``hardware_release``, ``travel`` and ``pulses``.
        """

        response = self.query_device("in")

        # decode the response
        header = response[0:3]
        ell = response[3:5]
        sn = response[5:13]
        year = response[13:17]
        firmware_release = response[17:19]
        hardware_release = response[19:21]

        bytes_travel = response[21:25]  # units: mm/deg

        binary_travel = bytes_to_binary(bytes_travel)
        travel = twos_complement_to_int(binary_travel)

        bytes_pulses = response[25:33]
        binary_pulses = bytes_to_binary(bytes_pulses)
        pulses = twos_complement_to_int(binary_pulses)

        outp = {
            "header": header,
            "ell": ell,
            "sn": sn,
            "year": year,
            "firmware_release": firmware_release,
            "hardware_release": hardware_release,
            "travel": travel,
            "pulses": pulses}
        return outp

    def get_device_status(self):
        """Query the device status code and map it to a human-readable string.

        Returns:
            dict: ``{"header", "status"}`` with ``status`` from ``DEVICE_STATUS_CODES``.

        Note:
            As written this references an undefined name ``Thorlabs_ELL8K`` and will
            raise ``NameError``. See the class-level note; the fix is non-surgical.
        """

        response = self.query_device("gs")
        # read response and decode it:
        header = response[0:3]
        byte_status = response[3:5]
        if self.debug > 0:
            print("Byte status:", byte_status)

        binary_status = bytes_to_binary(byte_status)
        if self.debug > 0:
            print("Binary status", binary_status)
        int_status = int(binary_status, base=2)

        if int_status in list(Thorlabs_ELL8K.DEVICE_STATUS_CODES.keys()):
            return {"header": header, "status": Thorlabs_ELL8K.DEVICE_STATUS_CODES[int_status]}
        else:
            return {"header": header, "status": Thorlabs_ELL8K.DEVICE_STATUS_CODES["OutOfBounds"]}

    def move_home(self, clockwise=True, blocking=True):
        """Move to the factory default home position.

        Resetting the home position (supported by the Thorlabs API) is intentionally not
        exposed here, as Thorlabs advises against it.

        Args:
            clockwise: Direction of the homing move.
            blocking: If True, wait until motion stops before returning.

        Returns:
            dict: Decoded status/position reply (see ``_decode_position_response``).
        """
        if clockwise:
            direction = 0
        else:
            direction = 1
        response = self.query_device("ho{0}".format(direction))

        if blocking:
            self._block_until_stopped()
        return self._decode_position_response(response)

    def move_absolute(self, angle, blocking=True):
        """Move to an absolute angle measured from the home position.

        Args:
            angle: Target angle in degrees.
            blocking: If True, wait until motion stops before returning.

        Returns:
            dict: Decoded status/position reply (see ``_decode_position_response``).
        """

        pulses_hex = self._angle_to_hex_pulses(angle)
        response = self.query_device("ma{0}".format(pulses_hex))
        header = response[0:3]
        if blocking:
            self._block_until_stopped()
        return self._decode_position_response(response)

    def move_relative(self, angle, blocking=True):
        """Move by an angle relative to the current position.

        Args:
            angle: Relative angle in degrees; negative values move the opposite way.
            blocking: If True, wait until motion stops before returning.

        Returns:
            dict: Decoded status/position reply (see ``_decode_position_response``).
        """
        pulses_hex = self._angle_to_hex_pulses(angle)
        response = self.query_device("mr{0}".format(pulses_hex))
        if blocking:
            self._block_until_stopped()
        return self._decode_position_response(response)

    def optimize_motors(self, save_new_params=False):
        """Run the motor frequency optimization routine.

        Load, build tolerances and other mechanical variances mean a motor's default
        resonant frequency may not give best performance. This triggers a frequency
        search (forward and backward) and tunes the operating frequencies; the resulting
        values are only persisted to the device when saved.

        Args:
            save_new_params: If True, persist the optimized parameters via
                ``save_new_parameters``.

        Returns:
            The raw reply to the optimize command.
        """
        reply = self.query_device('om')
        if save_new_params:
            self.save_new_parameters()
        return reply

    def save_new_parameters(self):
        """Persist the current motor parameters to the device's non-volatile memory.

        Returns:
            The raw reply to the save command.
        """
        return self.query_device('us')
