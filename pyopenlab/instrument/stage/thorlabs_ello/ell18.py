"""Driver and Qt UI for the Thorlabs ELL18 / ELL18K rotation stage."""

import sys

from pyopenlab.instrument.stage.thorlabs_ello import bytes_to_binary
from pyopenlab.instrument.stage.thorlabs_ello import ElloDevice
from pyopenlab.instrument.stage.thorlabs_ello import twos_complement_to_int
from pyopenlab.ui.ui_tools import *
from pyopenlab.utils.gui import *


class Ell18(ElloDevice):
    """Thorlabs ELL18(K) rotation stage.

    ``TRAVEL`` and ``PULSES_PER_REVOLUTION`` are read from the device at construction.
    """

    def __init__(self, *args, **kwargs):
        """Connect and read travel/pulse parameters from the device.

        Args:
            *args: Forwarded to ``ElloDevice.__init__`` (serial device, device index).
            **kwargs: Forwarded to ``ElloDevice.__init__`` (e.g. ``debug``).
        """
        super().__init__(*args, **kwargs)
        self.configuration = self.get_device_info()
        self.TRAVEL = self.configuration["travel"]
        self.PULSES_PER_REVOLUTION = self.configuration["pulses"]
        if self.debug > 0:
            print("Travel (degrees):", self.TRAVEL)
            print("Pulses per revolution", self.PULSES_PER_REVOLUTION)
            print("Device status:", self.get_device_status())

    def get_position(self, axis=None):
        """Query the stage and return its current angle in degrees.

        Overrides ``Stage.get_position``.

        Args:
            axis: Ignored; present for ``Stage`` interface compatibility.

        Returns:
            float: Current angle in degrees.

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
            degrees_position = self.TRAVEL * \
                (float(pulse_position)/self.PULSES_PER_REVOLUTION)
            return degrees_position
        else:
            raise ValueError("Incompatible Header received:{}".format(header))

    def move_absolute(self, angle, blocking=True):
        """Move to an absolute angle, wrapping the request into ``[0, 360)``.

        The stage only accepts non-negative angles, so out-of-range and negative inputs
        are folded modulo 360 before delegating to the base implementation.

        Args:
            angle: Target angle in degrees (any value; normalized internally).
            blocking: If True, wait until motion stops before returning.

        Returns:
            dict: Decoded status/position reply.
        """
        if -360 > angle or angle > 360:
            angle %= 360
        if angle < 0:
            angle = 360 + angle
        return super().move_absolute(angle, blocking=blocking)

    def get_qt_ui(self):
        """Return the Qt control widget for this stage."""
        return Thorlabs_ELL18K_UI(self)


class Thorlabs_ELL18K_UI(QtWidgets.QWidget, UiTools):
    """Qt widget for driving an ELL18K stage (relative/absolute/home moves)."""

    def __init__(self, stage, parent=None, debug=0):
        if not isinstance(stage, Ell18):
            raise ValueError("Object is not an instance of the Thorlabs_ELL18K Stage")
        super(Thorlabs_ELL18K_UI, self).__init__()

        self.stage = stage  # this is the actual rotation stage
        self.parent = parent
        self.debug = debug
        path = os.path.dirname(__file__)
        uic.loadUi(os.path.join(os.path.dirname(path), 'thorlabs_ell18k.ui'), self)

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
    """Exercise a stage's status, info and move commands; for manual testing."""
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
    """Launch the stage UI against a stage on COM11; for manual testing."""
    s = Ell18("COM11")
    app = get_qt_app()
    ui = Thorlabs_ELL18K_UI(stage=s)
    ui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":

    stage = Ell18("COM11", debug=False)
    app = get_qt_app()
    ui = Thorlabs_ELL18K_UI(stage)
    ui.show()
    sys.exit(app.exec_())
