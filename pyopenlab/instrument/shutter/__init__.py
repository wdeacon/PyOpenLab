"""Generic optical shutter instrument classes and a Qt UI.

This module defines the :class:`Shutter` base class shared by all shutter
drivers in PyOpenLab, the :class:`ShutterWithEmulatedRead` variant for devices
that cannot report their own state, a :class:`ShutterUI` Qt widget, and a
:class:`DummyShutter` used for testing.
"""

import contextlib
import os
import time

from pyopenlab.instrument import Instrument
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import get_qt_app
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic
from pyopenlab.utils.notified_property import DumbNotifiedProperty
from pyopenlab.utils.notified_property import register_for_property_changes


class Shutter(Instrument):
    """A generic instrument class for optical shutters.

    An optical shutter can be "Open" (allowing light to pass) or "Closed" (not
    allowing light through). This generic class provides a GUI and some
    convenience methods. The state of the shutter is exposed through the
    :attr:`state` property, a string that is either "Open" or "Closed". For a
    boolean answer use :meth:`is_open` or :meth:`is_closed`. :meth:`expose`
    opens the shutter for a number of seconds, and :meth:`toggle` changes state.

    Subclassing Notes:
        The minimum required subclassing effort is overriding :meth:`set_state`
        to open and close the shutter. Overriding :meth:`get_state` allows you
        to read back the state of the shutter. If you want to emulate that (i.e.
        keep track of the state of the shutter in software) subclass
        :class:`ShutterWithEmulatedRead` and make sure you call its
        ``__init__`` method in your initialisation code.
    """

    def __init__(self):
        super(Shutter, self).__init__()

    def toggle(self):
        """Toggle the state of the shutter.

        The default behaviour emulates a toggle command by reading the current
        state and setting the opposite one.

        Raises:
            NotImplementedError: If the shutter cannot report its state and so
                has no way to determine which state to toggle to.
        """
        try:
            if self.is_closed():
                self.state = "Open"
            else:
                self.state = "Closed"
        except NotImplementedError:
            raise NotImplementedError("This shutter has no way to toggle!"
                                      "")

    @contextlib.contextmanager
    def hold(self, state="Open", default_state="Closed"):
        """Hold the shutter in a given state for the duration of a ``with`` block.

        The shutter is held in ``state`` (default "Open") while the body of the
        ``with`` block runs, then returns to its previous state afterwards, even
        if exceptions occur.

        If the shutter can't report its current state it raises a
        :class:`NotImplementedError` (the default behaviour), in which case the
        shutter is restored to ``default_state`` afterwards instead.

        Args:
            state: The state to hold the shutter in during the block. Either
                "Open" or "Closed".
            default_state: The state to restore the shutter to afterwards if the
                previous state could not be read.

        Yields:
            None: Control is yielded to the body of the ``with`` block.

        Note:
            In the future this might block other threads from touching the
            shutter; currently it does not.
        """
        try:
            oldstate = self.state
        except NotImplementedError:
            oldstate = default_state
        try:
            self.state = state
            yield
        finally:
            self.state = oldstate

    def expose(self, time_in_seconds):
        """Open the shutter for a specified time, then close it again.

        This function blocks until the exposure is over.

        Args:
            time_in_seconds: How long to hold the shutter open, in seconds.

        Note:
            If you override this in a subclass, take care with reads/writes of
            the :attr:`state` property. In a subclass of
            :class:`ShutterWithEmulatedRead` you might need to update
            ``_last_set_state``.
        """
        with self.hold("Open"):
            time.sleep(time_in_seconds)

    def get_state(self):
        """Return whether the shutter is "Open" or "Closed".

        Returns:
            str: The current shutter state.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass that
                can read the hardware state.
        """
        raise NotImplementedError("This shutter has no way to get its state!"
                                  "")

    def set_state(self, value):
        """Set the shutter to be either "Open" or "Closed".

        Args:
            value: The desired state, either "Open" or "Closed".

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError("This shutter has no way to set its state!"
                                  "")

    def open_shutter(self):
        """Open the shutter."""
        self._set_state_proxy("Open")

    def close_shutter(self):
        """Close the shutter."""
        self._set_state_proxy("Closed")

    # The proxy methods let subclasses override get_state/set_state without
    # having to redefine the `state` property each time.
    def _get_state_proxy(self):
        """Return the shutter state by delegating to :meth:`get_state`.

        Returns:
            str: Either "Open" or "Closed".
        """
        return self.get_state()

    def _set_state_proxy(self, state):
        """Set the shutter state and cache it in ``_last_set_state``.

        Args:
            state: The desired state, either "Open" or "Closed".
        """
        self.set_state(state)
        self._last_set_state = state.title()  # Remember what state we're in

    state = property(_get_state_proxy, _set_state_proxy)

    def is_open(self):
        """Return ``True`` if the shutter is open.

        Returns:
            bool: Whether the shutter state is "Open".
        """
        return self.state.title() == "Open"

    def is_closed(self):
        """Return ``True`` if the shutter is closed.

        Returns:
            bool: Whether the shutter state is "Closed".
        """
        return self.state.title() == "Closed"

    def get_qt_ui(self):
        """Return a Qt graphical interface for the shutter.

        Returns:
            ShutterUI: A widget for controlling this shutter.
        """
        return ShutterUI(self)


class ShutterWithEmulatedRead(Shutter):
    """A shutter that keeps track in software of whether it's open.

    Use this instead of :class:`Shutter` if you don't want to (or can't)
    communicate with the shutter to check whether it's open or closed. The last
    state set via :attr:`state` is remembered and returned by :meth:`get_state`.

    Subclassing Notes:
        See the subclassing notes from :class:`Shutter`. All you need to
        override is :meth:`set_state`; the rest is dealt with. If you have to
        initialise the hardware, do that *before* calling
        ``ShutterWithEmulatedRead.__init__()`` as it closes the shutter to
        start with.
    """

    def __init__(self):
        """Initialise the shutter to the closed position."""
        self._last_set_state = 'Closed'
        self.state = "Closed"

    def get_state(self):
        """Return the last state the shutter was set to.

        Returns:
            str: Either "Open" or "Closed".
        """
        return self._last_set_state


class ShutterUI(QtWidgets.QWidget, UiTools):
    """A Qt widget for displaying and controlling a :class:`Shutter`."""

    def __init__(self, shutter, parent=None):
        """Build the shutter control widget.

        Args:
            shutter: The :class:`Shutter` instance this UI controls.
            parent: The parent Qt widget, if any.

        Raises:
            AssertionError: If ``shutter`` is not a :class:`Shutter` instance.
        """
        assert isinstance(shutter, Shutter), 'instrument must be a Shutter'
        self.shutter = shutter
        super(ShutterUI, self).__init__(parent)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'shutter.ui'), self)
        self.auto_connect_by_name(controlled_object=self.shutter, verbose=False)

    #    self.state.stateChanged.connect(self.on_change)

    def on_change(self):
        """Toggle the shutter in response to a UI state change."""
        self.shutter.toggle()


class DummyShutter(Shutter):
    """A stub shutter that holds its state in memory, for testing without hardware."""
    _open = DumbNotifiedProperty(False)

    def __init__(self):
        """Create a dummy shutter object, initially closed."""
        self._open = False
        super(DummyShutter, self).__init__()

    def toggle(self):
        """Toggle the state of the shutter."""
        self._open = not self._open

    def get_state(self):
        """Return the state of the shutter.

        Returns:
            str: "Open" or "Closed".
        """
        return "Open" if self._open else "Closed"

    def set_state(self, value):
        """Set the state of the shutter.

        Args:
            value: The desired state. A string ("Open"/"Closed", case
                insensitive) or a bool (``True`` for open).
        """
        if isinstance(value, str):
            self._open = (value.lower() == "open")
        elif isinstance(value, bool):
            self._open = value


if __name__ == '__main__':
    import sys
    app = get_qt_app()
    shutter = DummyShutter()

    state_peek = QuickControlBox(title="Internal State")
    state_peek.add_checkbox("_open", title="Shutter Open")
    state_peek.auto_connect_by_name(controlled_object=shutter)
    state_peek.show()

    ui = shutter.get_qt_ui()
    ui.show()
    sys.exit(app.exec_())
