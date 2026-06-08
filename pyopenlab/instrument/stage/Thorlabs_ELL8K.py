"""Driver for the Thorlabs ELL8K elliptical rotation stage over the ELLB bus."""

import sys
import time

import numpy as np

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.stage import Stage
from pyopenlab.instrument.stage.Thorlabs_ELL20 import BusDistributor
from pyopenlab.ui.ui_tools import *
from pyopenlab.utils.gui import *


def bytes_to_binary(bytearr, debug=0):
    """Convert an iterable of hex characters into a binary string.

    Args:
        bytearr: Iterable of hex digit characters.
        debug (int): If greater than 0, print intermediate values.

    Returns:
        str: Concatenated binary representation.
    """
    if debug > 0:
        print(bytearr)
    bytes_as_binary = [format(int(b, base=16), "#06b").replace("0b", "") for b in bytearr]
    if debug > 0:
        print(bytes_as_binary)
    binary = "".join(bytes_as_binary)
    return binary


def twos_complement_to_int(binary, debug=0):
    """Interpret a two's-complement binary string as a signed integer.

    Args:
        binary (str): Binary digit string, MSB first.
        debug (int): If greater than 0, print intermediate values.

    Returns:
        float: The signed value.
    """
    if debug > 0:
        print(binary)
    N = len(binary)
    a_N = int(binary[0])
    return float(-a_N * 2**(N - 1) + int(binary[1:], base=2))


def int_to_hex(integer, padded_length=8, debug=0):
    """Convert an integer to an upper-case, zero-padded hex string.

    Args:
        integer (int): Value to convert.
        padded_length (int): Minimum number of hex digits in the result.
        debug (int): Unused; retained for call-signature compatibility.

    Returns:
        str: Hex representation without the ``0x`` prefix.
    """
    outp = (format(integer, "#0{}x".format(padded_length + 2)).replace("0x", "")).upper()
    return outp


def int_to_twos_complement(integer, padded_length=16, debug=0):
    """Encode a signed integer as an (unsigned) two's-complement integer.

    Non-negative values are returned unchanged; negative values are converted
    to their two's-complement representation.

    Args:
        integer (int): Value to encode.
        padded_length (int): Padding applied to the intermediate binary form.
        debug (int): If greater than 0, print intermediate values.

    Returns:
        int: The (unsigned) two's-complement value.
    """
    # number is above 0 - return binary representation:
    if integer >= 0:
        return integer

    # number is below zero - return twos complement representation:
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


class Thorlabs_ELL8K(Stage):

    # default id is 0, but if multiple devices of same type connected may have others
    VALID_DEVICE_IDs = [str(v) for v in list(range(0, 11)) + ["A", "B", "C", "D", "E", "F"]]

    # How much a stage sleeps (in seconds) between successive calls to .get_position.
    # Used to make blocking calls to move_absolute and move_relative.
    BLOCK_SLEEPING_TIME = 0.1
    # Theshold for position accuracy when stage is meant to be stationary
    # If difference between successive calls to get_position returns value
    # whose difference is less than jitter - consider stage to have stopped
    POSITION_JITTER_THRESHOLD = 0.02

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
        """Connect to a stage on the ELLB bus and read its configuration.

        Args:
            serial_device: Either a :class:`BusDistributor` instance or a COM
                port string such as ``"COM5"`` (a new bus is created for it).
            device_index (int): Index of this device on the bus (0-F).
            debug (int): If greater than 0, print diagnostic output.

        Raises:
            ValueError: If ``device_index`` is not a valid device ID.
        """
        if type(serial_device) is str:
            self.serial_device = BusDistributor(serial_device)
        else:
            self.serial_device = serial_device
        self.debug = debug

        Stage.__init__(self)
        self.ui = None

        # configure stage parameters
        if str(device_index) not in Thorlabs_ELL8K.VALID_DEVICE_IDs:
            raise ValueError("Device ID: {} is not valid!".format(device_index))
        self.device_index = device_index

        configuration = self.get_device_info()
        self.TRAVEL = configuration["travel"]
        self.PULSES_PER_REVOLUTION = configuration["pulses"]

        if self.debug > 0:
            print("Travel (degrees):", self.TRAVEL)
            print("Pulses per revolution", self.PULSES_PER_REVOLUTION)
            print("Device status:", self.get_device_status())

    def query_device(self, query):
        """Send a query prefixed with this device's index and return the reply.

        Args:
            query (str): Command without the leading device index.

        Returns:
            str: The raw response from the device.
        """
        raw_query = "{0}{1}".format(self.device_index, query)
        if self.debug > 0:
            print("raw_query", raw_query)
        raw_response = self.serial_device.query(raw_query)
        if self.debug > 0:
            print("raw_response", raw_response)
        return raw_response

    def __angle_to_pulse_count(self, angle):
        """Convert an angle in degrees into the motor pulse count to reach it.

        Uses ``PULSES_PER_REVOLUTION / TRAVEL`` pulses per degree; both values
        are reported by the device at initialization. Used when sending move
        instructions to the stage.

        Args:
            angle (float): Target angle in degrees.

        Returns:
            int: Number of motor pulses.
        """
        pulse_per_deg = self.PULSES_PER_REVOLUTION / float(self.TRAVEL)
        pulses = int(np.rint(angle * pulse_per_deg))
        if self.debug > 0:
            print("Input angle:", angle)
            print("Pulses:", pulses)
        return pulses

    def __pulse_count_to_angle(self, pulse_count):
        """Convert a motor pulse count into an angle in degrees.

        Used when decoding responses received from the stage.

        Args:
            pulse_count (float): Number of motor pulses.

        Returns:
            float: Angle in degrees.
        """
        return float(self.TRAVEL) * pulse_count / self.PULSES_PER_REVOLUTION

    def __angle_to_hex_pulses(self, angle):
        """Convert an angle into the hex pulse count the stage expects.

        Args:
            angle (float): Target angle in degrees, in the range (-360, 360)
                exclusive.

        Returns:
            str: Hex-encoded, two's-complement pulse count.

        Raises:
            ValueError: If the angle is outside (-360, 360).
        """
        if angle < -360.0 or angle > 360.0:
            raise ValueError("Valid angle bounds are: (-360,360) [exclusive]")

        # convert angle to number of pulses used to drive motors:
        pulses_int = self.__angle_to_pulse_count(angle)
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

    def __hex_pulses_to_angle(self, hex_pulse_position):
        """Decode a hex pulse-count response into an angle.

        Args:
            hex_pulse_position (str): Hex-encoded pulse count from the stage.

        Returns:
            float: Angle in degrees.
        """
        binary_pulse_position = bytes_to_binary(hex_pulse_position)
        int_pulse_position = twos_complement_to_int(binary_pulse_position)
        return self.__pulse_count_to_angle(int_pulse_position)

    def __decode_position_response(self, response):
        """Decode a status/position response from a move or home command.

        Args:
            response (str): Raw response from ``move_absolute``,
                ``move_relative`` or ``move_home``.

        Returns:
            dict: ``{"header", "status"}`` if the stage is still moving, or
            ``{"header", "position"}`` if a position was returned. None if the
            header is unrecognised.
        """
        header = response[0:3]
        if header == "{0}GS".format(self.device_index):
            # still moving
            status_code = int(response[3:5], base=16)
            status = Thorlabs_ELL8K.DEVICE_STATUS_CODES[status_code]
            outp = {"header": header, "status": status}
            return outp
        elif header == "{0}PO".format(self.device_index):
            hex_pulse_position = response[3:11]
            position = self.__hex_pulses_to_angle(hex_pulse_position)
            outp = {"header": header, "position": position}
            return outp

    def __block_until_stopped(self):
        """Block until the stage stops moving.

        Polls ``get_position`` and assumes the stage has stopped once two
        successive readings differ by less than ``POSITION_JITTER_THRESHOLD``.
        Returns early on a KeyboardInterrupt.
        """
        stopped = False
        previous_angle = 0.0
        current_angle = 1.0

        try:
            while (stopped == False):
                time.sleep(Thorlabs_ELL8K.BLOCK_SLEEPING_TIME)
                current_angle = self.get_position()
                stopped = (np.absolute(current_angle - previous_angle)
                           < Thorlabs_ELL8K.POSITION_JITTER_THRESHOLD)
                previous_angle = current_angle
        except KeyboardInterrupt:
            return
        return

    def get_position(self, axis=None):
        """Query the stage for its current angle in degrees. Overrides Stage.

        Args:
            axis: Unused; present for Stage interface compatibility.

        Returns:
            float: Current angle in degrees.

        Raises:
            ValueError: If the response header is not a position reply.
        """
        response = self.query_device("gp")
        header = response[0:3]
        if header == "{0}PO".format(self.device_index):
            # position given in twos complement representation
            byte_position = response[3:11]
            binary_position = bytes_to_binary(byte_position)
            pulse_position = twos_complement_to_int(binary_position)
            degrees_position = self.TRAVEL * \
                (float(pulse_position)/self.PULSES_PER_REVOLUTION)
            return degrees_position
        else:
            raise ValueError("Incompatible Header received:{}".format(header))

    def move(self, pos, axis=None, relative=False):
        """Move the stage to an angle. Overrides Stage.

        Args:
            pos (float): Target angle in degrees, in the range (-360, 360).
            axis: Unused; present for Stage interface compatibility.
            relative (bool): If True, move relative to the current position;
                otherwise move to an absolute angle.
        """
        if relative:
            self.move_relative(pos)
        else:
            self.move_absolute(pos)

    def get_qt_ui(self):
        """Return (creating if needed) the Qt control widget for this stage."""
        if self.ui is None:
            self.ui = Thorlabs_ELL8K_UI(stage=self)
        return self.ui

    def get_device_info(self):
        """Query the device identity and motion parameters.

        Must be called at initialization: the ``travel`` and ``pulses`` values
        it extracts define the pulse-to-angle scaling for the stage. The ratio
        ``pulses / travel`` gives the number of pulses per degree.

        Returns:
            dict: Device information with keys ``header``, ``ell``, ``sn``,
            ``year``, ``firmware_release``, ``hardware_release``, ``travel``
            (angular range) and ``pulses`` (pulses over the full travel).
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
        """Query the device status code to check it is functioning correctly.

        Returns:
            dict: ``{"header", "status"}`` with a human-readable status string.
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
        """Move the stage to its factory default home location.

        Resetting the stage's home is supported by the Thorlabs API but is not
        implemented here, as Thorlabs advises against it.

        Args:
            clockwise (bool): Direction to home in; False homes anticlockwise.
            blocking (bool): If True, wait until the stage stops moving.

        Returns:
            dict: Decoded position/status response.
        """
        if clockwise:
            direction = 0
        else:
            direction = 1
        response = self.query_device("ho{0}".format(direction))

        if blocking:
            self.__block_until_stopped()
        return self.__decode_position_response(response)

    def move_absolute(self, angle, blocking=True):
        """Move to an absolute angle relative to the home setting.

        Angles outside (-360, 360) are wrapped modulo 360, and negative angles
        are mapped onto the equivalent positive angle before moving.

        Args:
            angle (float): Target angle in degrees.
            blocking (bool): If True, wait until the stage stops moving.

        Returns:
            dict: Decoded position/status response.
        """
        if -360 > angle or angle > 360:
            angle %= 360
        if angle < 0:
            angle = 360 + angle
        pulses_hex = self.__angle_to_hex_pulses(angle)
        response = self.query_device("ma{0}".format(pulses_hex))

        header = response[0:3]

        if blocking:
            self.__block_until_stopped()
        return self.__decode_position_response(response)

    def move_relative(self, angle, blocking=True):
        """Move relative to the current position.

        Args:
            angle (float): Relative angle in degrees. A negative value moves in
                the opposite direction.
            blocking (bool): If True, wait until the stage stops moving.

        Returns:
            dict: Decoded position/status response.
        """
        pulses_hex = self.__angle_to_hex_pulses(angle)
        response = self.query_device("mr{0}".format(pulses_hex))
        if blocking:
            self.__block_until_stopped()
        return self.__decode_position_response(response)

    def optimize_motors(self, save_new_params=False):
        """Fine-tune the motor operating frequencies for the current load.

        Load, build tolerances and other mechanical variation mean the default
        resonant frequency may not give the best performance. This runs a
        frequency search (the SEARCHFREQ routine is invoked first
        automatically), then optimises the forward and backward operating
        frequencies. The new values are only persisted if saved.

        Args:
            save_new_params (bool): If True, persist the optimised values via
                ``save_new_parameters``.

        Returns:
            str: Raw reply from the device.
        """
        reply = self.query_device('om')
        if save_new_params:
            self.save_new_parameters()
        return reply

    def save_new_parameters(self):
        """Persist the current motor parameters to device memory.

        Returns:
            str: Raw reply from the device.
        """
        return self.query_device('us')


class Thorlabs_ELL8K_UI(QtWidgets.QWidget, UiTools):
    """Qt control panel for relative/absolute moves and homing of an ELL8K."""

    def __init__(self, stage, parent=None, debug=0):
        if not isinstance(stage, Thorlabs_ELL8K):
            raise ValueError("Object is not an instance of the Thorlabs_ELL8K Stage")
        super(Thorlabs_ELL8K_UI, self).__init__()
        self.stage = stage  # this is the actual rotation stage
        self.parent = parent
        self.debug = debug

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'thorlabs_ell8k.ui'), self)

        self.move_relative_btn.clicked.connect(self.move_relative)
        self.move_absolute_btn.clicked.connect(self.move_absolute)
        self.move_home_btn.clicked.connect(self.move_home)
        self.current_angle_btn.clicked.connect(self.update_current_angle)

    def move_relative(self):
        try:
            angle = float(self.move_relative_textbox.text())
        except ValueError as e:
            print(e)
            return
        self.stage.move(pos=angle, relative=True)

    def move_absolute(self):
        try:
            angle = float(self.move_absolute_textbox.text())
        except ValueError as e:
            print(e)
            return
        self.stage.move(pos=angle, relative=False)

    def move_home(self):
        self.stage.move_home()

    def update_current_angle(self):
        angle = self.stage.get_position()
        self.current_angle_value.setText(str(angle))


def test_stage(s):
    """Exercise a stage's motion commands and print results (manual test)."""
    debug = False

    print("Status", s.get_device_status())
    print("Info", s.get_device_info())
    print("Homing", s.move_home())
    print("Home position", s.get_position())
    angle = 30
    s.move(angle, relative=True)
    print("30==", s.get_position())
    angle = -30
    s.move(angle, relative=True)
    print("-30==", s.get_position())

    angle = 150
    s.move(angle, relative=False)
    print("150==", s.get_position())

    angle = -10
    s.move(angle, relative=False)
    print("350==", s.get_position())


def test_ui():
    """Open the stage UI against a stage on COM1 (manual test)."""
    s = Thorlabs_ELL8K("COM1")
    app = get_qt_app()
    ui = Thorlabs_ELL8K_UI(stage=s)
    ui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":

    stage = Thorlabs_ELL8K("COM11", debug=False)
    stage.show_gui(False)
