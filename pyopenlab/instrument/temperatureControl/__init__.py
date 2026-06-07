# -*- coding: utf-8 -*-
"""Base mixin for temperature-control instruments.

Provides background-threaded temperature monitoring and range-checking that any
temperature-control instrument can inherit by subclassing
:class:`TemperatureControlMixin` and overriding :meth:`get_temperature`.
"""

import threading
import time

from pyopenlab.utils import monitor_property


class TemperatureControlMixin():
    """Mixin providing temperature monitoring and control for instruments.

    The mixin offers two background threads: a temperature-control thread that
    checks every second whether the temperature is within range and warns when
    it leaves that range, and a temperature-monitoring thread (via
    :func:`pyopenlab.utils.monitor_property`) that periodically records the
    temperature and keeps a rolling history.

    Note:
        The minimum required to subclass this is to override
        :meth:`get_temperature`. Instruments that can set a target should also
        override :meth:`set_target_temperature` and :meth:`get_target_temperature`.
    """

    def __init__(self):
        super(TemperatureControlMixin, self).__init__()

        self._control_thread = None
        self._controlling = False

    def get_temperature(self):
        """Return the current temperature.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError

    temperature = property(fget=get_temperature)

    def set_target_temperature(self, value):
        """Set the target (set-point) temperature.

        Args:
            value: The desired target temperature.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError

    def get_target_temperature(self):
        """Return the target (set-point) temperature.

        Returns:
            None: The base implementation returns nothing; subclasses should
            override this to report the instrument's set-point.
        """
        return

    target_temperature = property(fset=set_target_temperature, fget=get_target_temperature)

    def monitor_temperature(self, how_long=5, how_often=10, warn_limits=None):
        """Start a background thread that records the temperature over time.

        Args:
            how_long (int): How long a history to keep, in minutes.
            how_often (int): How often to add a value to the history, in seconds.
            warn_limits (tuple): A ``(min, max)`` pair; a warning is raised when the
                temperature falls below ``min`` or rises above ``max``. ``None`` disables
                the warning.
        """
        monitor_property(self, 'temperature', how_long * 60, how_often, warn_limits)

    def control_temperature(self, upper_target=None, lower_target=None):
        """Start a background thread that checks the temperature stays in range.

        If both limits are ``None`` and the ``target_temperature`` property has not been
        set, an upper limit of 1000 is assumed. Starting a new control thread stops any
        previously running one.

        Args:
            upper_target (float): Upper temperature limit; a warning is logged if exceeded.
            lower_target (float): Lower temperature limit; a warning is logged if breached.
        """
        if upper_target is None and lower_target is None:
            if self.target_temperature is not None:
                upper_target = self.target_temperature
            else:
                upper_target = 1000
        if self._control_thread is not None:
            self._controlling = False
            self._control_thread.join()
            del self._control_thread
        self._control_thread = threading.Thread(target=self._control_temperature,
                                                args=(upper_target, lower_target))
        self._controlling = True
        self._control_thread.start()

    def _control_temperature(self, upper_temp=None, lower_temp=None):
        """Loop until the temperature leaves the range, then log a warning.

        Args:
            upper_temp (float): Upper temperature limit.
            lower_temp (float): Lower temperature limit.

        Note:
            The loop guard ``upper_temp > self.temperature > lower_temp`` raises a
            ``TypeError`` when either limit is ``None`` (e.g. when only one of
            ``upper_target``/``lower_target`` is supplied to
            :meth:`control_temperature`).
        """
        while upper_temp > self.temperature > lower_temp:
            time.sleep(1)
            if not self._controlling:
                break
        self._logger.warn('Temperature out of range')
