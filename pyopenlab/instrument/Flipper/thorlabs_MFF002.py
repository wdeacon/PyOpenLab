"""Driver for the Thorlabs MFF series motorised filter flipper."""

import struct
import time

import numpy as np
import serial

from pyopenlab.instrument.Flipper import Flipper
from pyopenlab.utils.thread_utils import background_action
from pyopenlab.utils.thread_utils import locked_action


class ThorlabsMFF(Flipper):
    """Thorlabs MFF motorised flip mount, controlled over the APT protocol."""

    port_settings = dict(baudrate=115200,
                         bytesize=8,
                         parity=serial.PARITY_NONE,
                         stopbits=1,
                         xonxoff=0,
                         rtscts=0,
                         timeout=5,
                         writeTimeout=1)

    def __init__(self, port, **kwargs):
        """Connect to an MFF flipper.

        Args:
            port: Serial port the flipper is on (e.g. ``'COM19'``).
            **kwargs: Accepted for interface compatibility; currently unused.
        """
        Flipper.__init__(self, port)

    @locked_action
    def set_state(self, value):
        """Move the flipper to the requested position and wait for completion.

        Args:
            value: Truthy to move to position 1, falsy to move to position 2/0.

        Raises:
            RuntimeError: If the move does not complete within the port timeout.
        """
        if value:
            self.write(0x046A, param1=0x01, param2=0x01)
            time.sleep(0.1)
            t0 = time.time()
            while self.get_state() != 1:
                time.sleep(0.1)
                if time.time() - t0 > self.port_settings['timeout']:
                    raise RuntimeError('Timed out while waiting for position change')
        else:
            self.write(0x046A, param1=0x01, param2=0x02)
            time.sleep(0.1)
            t0 = time.time()
            while self.get_state() != 0:
                time.sleep(0.1)
                if time.time() - t0 > self.port_settings['timeout']:
                    raise RuntimeError('Timed out while waiting for position change')

    def get_state(self):
        """Query and decode the flipper's current position.

        Returns:
            ``1`` or ``0`` for the two valid positions. A sentinel string is
            returned if the status bits are inconsistent (see Note).

        Note:
            On an unexpected status mask this returns the placeholder strings
            ``'Fuck'``/``'Fuck2'`` rather than raising. Callers comparing the
            result to ``0``/``1`` should treat any non-int return as an error.
        """
        self.write(0x0429, param1=0x01)
        read = self.read()
        msg = read['data']
        unpacked = self.unpack_binary_mask(struct.unpack('<HI', msg)[1])
        if np.sum(unpacked) != 1:
            return 'Fuck'
        elif unpacked[1]:
            return 0
        elif unpacked[0]:
            return 1
        else:
            return 'Fuck2'


if __name__ == '__main__':
    import sys

    # from pyopenlab.utils.gui import *
    # app = get_qt_app()
    flipper = ThorlabsMFF('COM19')

    # flipper.get_status()
    # print flipper.model
    # flipper.set_state(0)
    # time.sleep(2)
    # print flipper.get_status()
    # #time.sleep(2)
    # flipper.set_state(1)
    # time.sleep(2)
    # print flipper.get_status()

    # print flipper.state
    # flipper.state = 0
    # print flipper.state
    # print flipper._last_set_state
    # ui = flipper.get_qt_ui()
    # ui.show()
    # sys.exit(app.exec_())
    flipper.show_gui()
