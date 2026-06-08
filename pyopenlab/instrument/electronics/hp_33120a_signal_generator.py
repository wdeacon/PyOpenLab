"""VISA driver for the HP/Agilent 33120A function/signal generator."""

__author__ = 'alansanders'

from functools import partial

from pyopenlab.instrument.visa_instrument import queried_property
from pyopenlab.instrument.visa_instrument import VisaInstrument


class SignalGenerator(VisaInstrument):
    """HP 33120A signal generator, exposing its settings as properties."""

    def __init__(self, address='GPIB0::3::INSTR'):
        """Open VISA communication with the signal generator.

        Args:
            address: VISA resource address.
        """
        super(SignalGenerator, self).__init__(address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'

    frequency = queried_property('freq?', 'freq {0}', doc='Output frequency in Hz')
    function = queried_property('function:shape?',
                                'function:shape {0}',
                                validate=['sinusoid', 'dc'],
                                dtype='str',
                                doc="Output waveform shape ('sinusoid' or 'dc')")
    voltage = queried_property('voltage?', 'voltage {0}', doc='Output amplitude in volts')
    offset = queried_property('voltage:offset?', 'voltage:offset {0}', doc='DC offset in volts')
    output_load = queried_property('output:load?',
                                   'output:load {0}',
                                   validate=['inf'],
                                   dtype='str',
                                   doc='Output load impedance')
    volt_high = queried_property('volt:high?', 'volt:high {0}', doc='High voltage level in volts')
    volt_low = queried_property('volt:low?', 'volt:low {0}', doc='Low voltage level in volts')
    output = queried_property('output?',
                              'output {0}',
                              validate=['OFF', 'ON'],
                              dtype='str',
                              doc="Output state ('ON' or 'OFF')")

    def reset(self):
        """Reset the generator to its default state (``*RST``)."""
        self.write('*rst')


if __name__ == '__main__':
    s = SignalGenerator(address='USB0::0x0957::0x0407::MY44037109::0::INSTR')
    print(s.frequency)
    s.frequency = 1e3
    print(s.frequency)
    print(s.function)
    s.function = 'sinusoid'
    print(s.function)
