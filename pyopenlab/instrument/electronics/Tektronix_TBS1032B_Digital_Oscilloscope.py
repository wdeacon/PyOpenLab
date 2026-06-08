# -*- coding: utf-8 -*-
"""VISA driver for the Tektronix TBS1032B digital storage oscilloscope.

Note:
    Importing this module instantiates a ``TBS1032B`` at the bottom of the file
    (``o = TBS1032B(...)``), which attempts to open a VISA connection on import.
    This is a pre-existing bug left for a later code pass.
"""

from functools import partial

from pyopenlab.instrument.visa_instrument import queried_property
from pyopenlab.instrument.visa_instrument import VisaInstrument


class TBS1032B(VisaInstrument):
    """VISA interface for the Tektronix TBS1032B digital oscilloscope."""

    def __init__(self, address='GPIB0::3::INSTR'):
        """Open VISA communication with the oscilloscope.

        Args:
            address: VISA resource address.
        """
        super(TBS1032B, self).__init__(address)

    def channel(self, channel):
        """Select the channel used for immediate measurements.

        Args:
            channel: Channel number to measure from.
        """
        self.write('MEASUrement:IMMed:SOUrce CH' + str(channel))

    def set_probe(self, channel, probe):
        """Set the probe attenuation for a channel.

        Args:
            channel: Channel number.
            probe: Probe attenuation factor.
        """
        self.write('CH' + str(channel) + ':PRObe' + str(probe))

    def autoset(self):
        """Run the scope's autoset to fit the current signal."""
        self.write('AUTOSet EXECute')

    def acquisition(self, acq):
        """Start or stop acquisition.

        Args:
            acq: ``'RUN'`` or ``'STOP'``.
        """
        self.write('ACQuire:STATE ' + str(acq))

    def read_par(self, channel, parameter):
        """Measure a named parameter on a channel.

        Args:
            channel: Channel number to measure.
            parameter: Parameter name (many aliases accepted, e.g. ``'freq'``,
                ``'Vpp'``, ``'mean'``, ``'probe'``).

        Returns:
            tuple: ``(value_type, value)``; ``('Nothing', None)`` if the
            parameter is not recognised.
        """
        avoid_random_output = False

        if parameter in ['frequency', 'freq', 'Frequency', 'Freq', 'FREQUENCY', 'FREQ']:
            par = 'FREQuency'
        elif parameter in ['Mean', 'mean', 'MEAN']:
            par = 'MEAN'
        elif parameter in ['period', 'per', 'Period', 'PERIOD', 'PER']:
            par = 'PERIod'
        elif parameter in ['phase', 'Phase', 'PHASE']:
            par = 'PHAse'
        elif parameter in ['peak-peak', 'peak_to_peak', 'V_pp', 'pk2pk', 'Vpp', 'VPP']:
            par = 'PK2pk'
        elif parameter in ['Vrms', 'Voltage_rms']:
            par = 'CRMs'
        elif parameter in ['minimum', 'min', 'Minimum', 'Min']:
            par = 'MINImum'
        elif parameter in ['maximum', 'max', 'Maximum', 'Max']:
            par = 'MAXImum'
        elif parameter in ['rise', 'Rise']:
            par = 'RISe'
        elif parameter in ['Fall', 'fall']:
            par = 'FALL'
        elif parameter in ['ampl', 'amplitude', 'Amplitude', 'Ampl', 'AMPLITUDE', 'AMPL']:
            par = 'amplitude'
        elif parameter in ['attenuation', 'probe', 'att']:
            par = 'CH' + str(channel) + ':PRObe?'
            return self.output_typo_adjust('probe', self.query(str(par)))
        else:
            print('Having problem reading oscilloscope query')
            avoid_random_output = True

        if (avoid_random_output == False) and (parameter not in ['attenuation', 'probe', 'att']):
            self.write('MEASUrement:IMMed:TYPe ' + str(par))
            a = self.query('MEASUrement:IMMed:TYPe?')
            b = self.query('MEASUrement:IMMed:VALue?')
            return self.output_typo_adjust(a, b)
        else:
            return ('Nothing', None)

    def output_typo_adjust(self, a, b):
        """Strip trailing newlines from a measurement type/value pair.

        Args:
            a: Measurement type string.
            b: Measurement value string.

        Returns:
            tuple: ``(type, value)`` with ``value`` coerced to float when it had
            a trailing newline.
        """
        a = a
        b = b
        if a[len(a) - 1] == '\n':
            a = a[:len(a) - 1]
        if b[len(b) - 1] == '\n':
            b = float(b[:len(b) - 1])

        return (a, b)


o = TBS1032B(address='USB0::0x0699::0x0368::C010300::0::INSTR')
