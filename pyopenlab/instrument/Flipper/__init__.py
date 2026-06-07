"""Base classes for motorised optical flippers.

Defines the generic :class:`Flipper` interface (built on the Thorlabs APT
virtual-COM-port protocol), a Qt UI wrapper, and a software-only
:class:`Dummyflipper` for testing without hardware.
"""

import contextlib
import os
import time

from pyopenlab.instrument import Instrument
from pyopenlab.instrument.apt_virtual_com_port import APT_VCP
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import get_qt_app
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic
from pyopenlab.utils.notified_property import DumbNotifiedProperty
from pyopenlab.utils.notified_property import register_for_property_changes


class Flipper(APT_VCP):
    """A generic instrument class for flippers.

    The minimum required subclassing effort is overriding :meth:`set_state` and
    :meth:`get_state` to open and close the flipper. Overriding ``get_state``
    allows you to read back the state of the flipper. State is represented as
    ``0`` (closed) or ``1`` (open), exposed through the :attr:`state` property.
    """

    def __init__(self, port):
        """Open a flipper connection over the APT virtual COM port.

        Args:
            port: Serial port the flipper is connected to (e.g. ``'COM19'``).
        """
        APT_VCP.__init__(self, port=port, destination=0x50)

    def toggle(self):
        """Toggle the state of the flipper.

        Reads the current state and sets the opposite. The default behaviour
        emulates a toggle command when the hardware has none.

        Raises:
            NotImplementedError: If the flipper cannot toggle its state.
        """
        try:
            if self.state:
                self.state = 0
            else:
                self.state = 1
        except NotImplementedError:
            raise NotImplementedError("This flipper has no way to toggle!"
                                      "")

    def get_state(self):
        """Read back the current flipper state.

        Returns:
            The current state of the flipper.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError("This flipper has no way to get its state!"
                                  "")

    def set_state(self, value):
        """Set the flipper position.

        Args:
            value: Target state, ``0`` (closed) or ``1`` (open).

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError("This flipper has no way to set its state!"
                                  "")

    # Defining the proxy methods here means subclasses don't have to redefine
    # the `state` property every time they override get/set_state.
    def _get_state_proxy(self):
        """Return the flipper state by delegating to :meth:`get_state`."""
        return self.get_state()

    def _set_state_proxy(self, state):
        self.set_state(state)
        self._last_set_state = state  # Remember the last commanded state.

    state = property(_get_state_proxy, _set_state_proxy)

    def get_qt_ui(self):
        """Return a Qt graphical interface for the flipper.

        Returns:
            flipperUI: A widget bound to this flipper instance.
        """
        return flipperUI(self)


class flipperUI(QtWidgets.QWidget, UiTools):
    """Qt widget providing manual control of a :class:`Flipper`."""

    def __init__(self, flipper, parent=None):
        """Build the flipper control widget.

        Args:
            flipper: The :class:`Flipper` instance to control.
            parent: Optional parent Qt widget.

        Raises:
            AssertionError: If ``flipper`` is not a :class:`Flipper`.
        """
        assert isinstance(flipper, Flipper), 'instrument must be a flipper'
        self.flipper = flipper
        super(flipperUI, self).__init__(parent)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'flipper.ui'), self)
        self.auto_connect_by_name(controlled_object=self.flipper, verbose=False)

    #    self.state.stateChanged.connect(self.on_change)

    def on_change(self):
        """Toggle the flipper in response to a UI state change."""
        self.flipper.toggle()


class Dummyflipper(Flipper):
    """A stub class that simulates a flipper in software.

    Note:
        ``__init__`` calls ``super().__init__()`` without the ``port`` argument
        required by :class:`Flipper`/``APT_VCP``, so instantiating this class as
        written raises ``TypeError``. See the runtime-bug log in the PR notes.
    """
    _open = DumbNotifiedProperty(False)

    def __init__(self):
        """Create a dummy flipper object, initially closed."""
        self._open = False
        super(Dummyflipper, self).__init__()

    def toggle(self):
        """Toggle the simulated flipper between open and closed."""
        self._open = not self._open

    def get_state(self):
        """Return the simulated state.

        Returns:
            str: ``'Open'`` if open, otherwise ``'Closed'``.
        """
        return "Open" if self._open else "Closed"

    def set_state(self, value):
        """Set the simulated state.

        Args:
            value: ``str`` (``'open'``/``'closed'``, case-insensitive) or ``bool``.
                Values of other types are ignored.
        """
        if isinstance(value, str):
            self._open = (value.lower() == "open")
        elif isinstance(value, bool):
            self._open = value


if __name__ == '__main__':
    import sys
    import time

    # app = get_qt_app()
    # flipper = Dummyflipper()
    # flipper.setstate(0)
    # time.sleep(5)
    # flipper.set_state(1)
    # state_peek = QuickControlBox(title="Internal State")
    # state_peek.add_checkbox("_open", title="flipper Open")
    # state_peek.auto_connect_by_name(controlled_object=flipper)
    # state_peek.show()
    # ui = flipper.get_qt_ui()
    # ui.show()
    # sys.exit(app.exec_())
