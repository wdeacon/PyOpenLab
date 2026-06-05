"""VISA driver for Agilent/Keysight DSO-X 2000-series oscilloscopes."""
from __future__ import print_function

from builtins import object

__author__ = 'alansanders'

from functools import partial

import matplotlib.pyplot as plt
import numpy as np

from pyopenlab.instrument.visa_instrument import queried_channel_property
from pyopenlab.instrument.visa_instrument import queried_property
from pyopenlab.instrument.visa_instrument import VisaInstrument
from pyopenlab.ui.ui_tools import *
from pyopenlab.utils.gui import *


class AgilentDSOChannel(object):
    """One input channel of an :class:`AgilentDSO`, exposing its SCPI settings.

    The ``display``, ``range``, ``scale``, ``offset``, ``coupling``, ``units``,
    ``label`` and ``probe`` attributes are channel-scoped queried properties.
    """

    def __init__(self, dso, channel):
        """Bind this channel to its parent scope.

        Args:
            dso: The owning :class:`AgilentDSO`.
            channel: The channel number this object represents.
        """
        self.parent = dso
        self.ch = channel

    def capture(self):
        """Digitize this channel into the scope's acquisition memory."""
        self.parent.write(':digitize channel{0}'.format(self.ch))

    display = queried_channel_property(':channel{0}:display?',
                                       ':channel{0}:display {1}',
                                       validate=[0, 1],
                                       dtype='int')
    range = queried_channel_property(':channel{0}:range?', ':channel{0}:range {1}')
    scale = queried_channel_property(':channel{0}:scale?', ':channel{0}:scale {1}')
    offset = queried_channel_property(':channel{0}:offset?', ':channel{0}:offset {1}')
    coupling = queried_channel_property(':channel{0}:coupling?',
                                        ':channel{0}:coupling {1}',
                                        validate=['ac', 'dc'],
                                        dtype='str')
    units = queried_channel_property(':channel{0}:unit?',
                                     ':channel{0}:unit {1}',
                                     validate=['volt', 'ampere'],
                                     dtype='str')
    label = queried_channel_property(':channel{0}:label?', ':channel{0}:label {1}', dtype='str')
    probe = queried_channel_property(':channel{0}:probe?', ':channel{0}:probe {1}')


class AgilentDSO(VisaInstrument):
    """Interface to Agilent/Keysight digital storage oscilloscopes.

    Acquisition, timebase, trigger and waveform settings are exposed as queried
    properties (e.g. :attr:`time_range`, :attr:`trigger_level`). Per-channel
    settings live on the :class:`AgilentDSOChannel` objects in :attr:`channels`.
    """

    def __init__(self, address='USB0::0x0957::0x1799::MY51330673::INSTR'):
        """Open VISA communication and create the channel objects.

        Args:
            address: VISA resource address.
        """
        super(AgilentDSO, self).__init__(address=address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.channel_names = (1, 2)
        for ch in self.channel_names:
            setattr(self, 'channel{0}'.format(ch), AgilentDSOChannel(self, ch))
        self.channels = tuple(getattr(self, 'channel{0}'.format(ch)) for ch in self.channel_names)
        # set byte transmission
        self.waveform_format = 'byte'
        byteorder = self.waveform_byteorder
        self.waveform_unsigned = 1
        byteorder = True if byteorder == 'MSBF' else False
        self.instr.values_format.use_binary('B', byteorder, np.array)

    def reset(self):
        """Reset the scope to its default state (``*RST``)."""
        self.write('*rst')

    def clear(self):
        """Clear the scope's status registers (``*CLS``)."""
        self.write('*cls')

    def autoscale(self):
        """Auto-scale the display to the current signals."""
        self.write(':autoscale')

    def capture(self, channel=None):
        """Digitize one or all channels into acquisition memory.

        Args:
            channel: A channel from :attr:`channels` to digitize, or ``None``
                to digitize all channels.
        """
        if channel is None:
            self.write(':digitize')
        else:
            assert channel in self.channels
            self.write(':digitize channel{0}'.format(channel))

    def run(self):
        """Start continuous acquisition."""
        self.write(':run')

    def single_shot(self):
        """Arm the scope for a single acquisition."""
        self.write(':single')

    def stop(self):
        """Stop acquisition."""
        self.write(':stop')

    def force_trigger(self):
        """Force an immediate trigger."""
        self.write(':trigger:force')

    acquire_type = queried_property(':acquire:type?',
                                    ':acquire:type {0}',
                                    validate=['normal', 'average', 'hresolution', 'peak'],
                                    dtype='str')
    acquire_complete = queried_property(':acquire:complete?', ':acquire:complete {0}')
    acquire_count = queried_property(':acquire:count?', ':acquire:count {0}')
    acquire_points = queried_property(':acquire:points?', dtype='int')
    armed = queried_property(':aer?')
    opc = queried_property('*opc?')
    operegister_condition = queried_property(':operegister:condition?', dtype='int')
    time_mode = queried_property(':timebase:mode?',
                                 ':timebase:mode {0}',
                                 validate=['main', 'window', 'xy', 'roll', 'MAIN'],
                                 dtype='str')
    time_range = queried_property(':timebase:range?', ':timebase:range {0}')
    time_scale = queried_property(':timebase:scale?', ':timebase:scale {0}')
    time_ref = queried_property(':timebase:reference?',
                                ':timebase:reference {0}',
                                validate=['left', 'center', 'right', 'LEFT', 'CENT'],
                                dtype='str')
    time_delay = queried_property(':timebase:delay?', ':timebase:delay {0}')
    trigger_sweep = queried_property(':trigger:sweep?',
                                     ':trigger:sweep {0}',
                                     validate=['normal', 'auto', 'NORM', 'AUTO'],
                                     dtype='str')
    trigger_mode = queried_property(':trigger:mode?',
                                    ':trigger:mode {0}',
                                    validate=['edge', 'glitch', 'pattern', 'tv', 'EDGE'],
                                    dtype='str')
    trigger_level = queried_property(':trigger:level?', ':trigger:level {0}')
    trigger_source = queried_property(':trigger:source?',
                                      ':trigger:source {0}',
                                      validate=[
                                          'channel1', 'channel2', 'external', 'line', 'wgen',
                                          'CHAN1', 'CHAN2'],
                                      dtype='str')
    trigger_slope = queried_property(':trigger:slope?',
                                     ':trigger:slope {0}',
                                     validate=[
                                         'positive', 'negative', 'either', 'alternate', 'POS',
                                         'NEG'],
                                     dtype='str')
    trigger_reject_noise = queried_property(':trigger:nreject?',
                                            ':trigger:nreject {0}',
                                            validate=[0, 1],
                                            dtype='int')
    trigger_filter = queried_property(':trigger:hfreject?',
                                      ':trigger:hfreject {0}',
                                      validate=[0, 1],
                                      dtype='int')
    trigger_status = queried_property(':ter?', dtype='int')
    waveform_format = queried_property(':waveform:format?',
                                       ':waveform:format {0}',
                                       validate=['byte', 'ascii'],
                                       dtype='str')
    waveform_byteorder = queried_property(':waveform:byteorder?',
                                          ':waveform:byteorder {0}',
                                          validate=[
                                              'lsbfirst', 'msbfirst', 'LSBFirst', 'MSBFirst',
                                              'LSBF', 'MSBF'],
                                          dtype='str')
    waveform_unsigned = queried_property(':waveform:unsigned?',
                                         ':waveform:unsigned {0}',
                                         validate=[0, 1],
                                         dtype='int')
    waveform_points = queried_property(':waveform:points?', ':waveform:points {0}', dtype='int')
    waveform_points_mode = queried_property(':waveform:points:mode?',
                                            ':waveform:points:mode {0}',
                                            validate=[
                                                'normal', 'maximum', 'raw', 'NORM', 'MAX', 'RAW'],
                                            dtype='str')

    # read parameters
    def set_source(self, ch):
        """Select the channel that subsequent waveform reads come from.

        Args:
            ch: Channel number, one of :attr:`channel_names`.
        """
        assert ch in self.channel_names
        self.write(":waveform:source channel{0}".format(ch))

    x_or = queried_property(":waveform:xorigin?")
    x_inc = queried_property(":waveform:xincrement?")
    y_or = queried_property(":waveform:yorigin?")
    y_inc = queried_property(":waveform:yincrement?")
    y_ref = queried_property(":waveform:yreference?")

    def set_trace_parameters(self, ch, mode='maximum'):
        """Configure the waveform source and point count before a read.

        Args:
            ch: Channel number to read from.
            mode: Waveform points mode (e.g. ``'maximum'``, ``'normal'``,
                ``'raw'``).
        """
        assert ch in self.channel_names
        self.set_source(ch)
        self.waveform_points_mode = mode
        self.waveform_points = self.acquire_points

    def scale_trace(self, trace):
        """Convert a raw trace to physical (time, voltage) arrays.

        Args:
            trace: Raw sample values from the scope.

        Returns:
            tuple: ``(time, trace)`` arrays in seconds and volts.
        """
        trace = self.y_or + (self.y_inc * (trace - self.y_ref))
        time = np.arange(trace.size) * self.x_inc + self.x_or
        return time, trace

    def read_trace(self, ch, renew=True):
        """Acquire and scale a waveform from a channel.

        Args:
            ch: Channel number to read.
            renew: If True, reconfigure the trace parameters first.

        Returns:
            tuple: ``(time, trace)`` arrays in seconds and volts.
        """
        assert ch in self.channel_names
        if renew:
            self.set_trace_parameters(ch)
        self.set_source(ch)
        trace = self.instr.query_values(':waveform:data?')

        time, trace = self.scale_trace(trace)
        return time, trace

    def check_trigger(self, force=False):
        """Return whether the scope has triggered.

        Args:
            force: If True, force a trigger before checking.

        Returns:
            bool: True if the trigger event register is set.
        """
        if force:
            self.force_trigger()
        return bool(self.trigger_status)

    def is_running(self):
        """Return whether the scope is currently acquiring.

        Returns:
            bool: False if the operation register shows the stopped state.
        """
        if (self.operegister_condition == 4128):
            return False
        else:
            return True

    def get_qt_ui(self):
        """Return the Qt control widget for this scope.

        Returns:
            AgilentDsoUI: A widget bound to this instrument.
        """
        return AgilentDsoUI(self)


class AgilentDsoUI(QtWidgets.QWidget, UiTools):
    """Qt control panel for an :class:`AgilentDSO`."""

    def __init__(self, dso, parent=None):
        """Build the UI for a scope.

        Args:
            dso: The :class:`AgilentDSO` to control.
            parent: Optional parent widget.

        Raises:
            ValueError: If ``dso`` is not an :class:`AgilentDSO`.
        """
        if not isinstance(dso, AgilentDSO):
            raise ValueError('dso must be an instance of DSO')
        super(AgilentDsoUI, self).__init__()
        self.dso = dso
        self.parent = parent
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'agilent_dso.ui'), self)


if __name__ == '__main__':
    dso = AgilentDSO()
    dso.trigger_sweep = 'auto'
    print(dso.time_range)
    print(dso.channel1.range)
    dso.capture()
    t, v = dso.read_trace(1)

    plt.plot(1e3 * t, v)
    plt.show()

    print(dso.check_trigger(force=True))
    dso.single_shot()
    print(dso.check_trigger(force=False))
    while not dso.check_trigger(force=False):
        continue
    print('triggered')
