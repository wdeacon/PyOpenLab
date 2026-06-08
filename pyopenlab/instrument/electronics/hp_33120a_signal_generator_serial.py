"""Serial driver for the HP/Agilent 33120A function/signal generator."""

__author__ = 'alansanders'

from functools import partial

import serial

from pyopenlab.instrument.message_bus_instrument import queried_property
from pyopenlab.instrument.serial_instrument import SerialInstrument


class SignalGenerator(SerialInstrument):
    """HP 33120A signal generator over a serial port, settings as properties."""
    port_settings = dict(
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  #wait at most one second for a response
        writeTimeout=1,  #similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=True,
    )

    def __init__(self, port=None):
        """Open the serial port and put the generator into remote mode.

        Args:
            port: Serial port name. ``None`` triggers interactive selection.
        """
        SerialInstrument.__init__(self, port=port)  #this opens the port
        self.query("SYST:REMOTE")

    frequency = queried_property('freq?', 'freq {0}', doc='Output frequency in Hz')
    function = queried_property('function:shape?',
                                'function:shape {0}',
                                validate=['sinusoid', 'dc', 'square'],
                                dtype='str',
                                doc="Output waveform shape ('sinusoid', 'dc' or 'square')")
    voltage = queried_property('voltage?', 'voltage {0}', doc='Output amplitude in volts')
    offset = queried_property('voltage:offset?', 'voltage:offset {0}', doc='DC offset in volts')
    output_load = queried_property('output:load?',
                                   'output:load {0}',
                                   validate=['inf'],
                                   dtype='str',
                                   doc='Output load impedance')
    volt_high = queried_property('volt:high?', 'volt:high {0}', doc='High voltage level in volts')
    volt_low = queried_property('volt:low?', 'volt:low {0}', doc='Low voltage level in volts')

    def reset(self):
        """Reset the generator to its default state (``*RST``)."""
        self.write('*rst')


if __name__ == '__main__':
    s = SignalGenerator("COM10")
#    print s.frequency
#    s.frequency = 1e3
#    print s.frequency
#    s.frequency = 2e3
#    print s.frequency
#    print s.function
#    s.function = 'sinusoid'
#    print s.function
