"""Thorlabs BSC103 three-channel benchtop stepper controller (APT serial)."""
import math
import struct
import sys

import numpy as np

from pyopenlab.instrument.apt_virtual_com_port import APT_VCP
from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.instrument.stage import Stage
from pyopenlab.ui.ui_tools import *
from pyopenlab.utils.gui import *


class Thorlabs_BSC103(APT_VCP):
    """Minimal APT connection to a BSC103 controller (motherboard at 0x11).

    This is a stub: it only opens the serial link with the BSC103 motherboard as
    the single APT destination and does not yet implement motion commands.
    """

    def __init__(self, port=None, debug=0):
        """Open the APT serial connection to the BSC103 motherboard.

        Args:
            port: Serial port name (e.g. ``'/dev/ttyUSB0'``).
            debug: Stored on the instance for optional debug output.
        """
        self.debug = debug
        APT_VCP.__init__(self, port=port, source=0x01, destination={"motherboard": 0x11})


if __name__ == "__main__":
    import struct
    t = Thorlabs_BSC103("/dev/ttyUSB0")

    formated_message = bytearray(struct.pack('BBBBBB', 0x23, 0x02, 0x01, 0x00, 0x11, 0x01))
    print(formated_message)
    # print t.query(message_id = msg_id,destination_id="motherboard")
    t.ser.write(formated_message)
    # print t.get_hardware_info(destination_id="motherboard")
