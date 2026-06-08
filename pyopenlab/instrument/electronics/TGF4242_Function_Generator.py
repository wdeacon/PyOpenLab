# -*- coding: utf-8 -*-
"""Serial driver for the Aim-TTi TGF4242 dual-channel function generator."""
import pyopenlab
from pyopenlab.instrument.serial_instrument import SerialInstrument


class TGF4242(SerialInstrument):
    """Serial interface to the TGF4242 function generator.

    Note:
        Commands require a space between the keyword and its value (e.g.
        ``'CHN 1'``); this is handled by each method below.
    """

    def __init__(self, port=None):
        """Open the serial port to the function generator.

        Args:
            port: Serial port name. ``None`` triggers interactive selection.
        """
        SerialInstrument.__init__(self, port=port)  #this opens the port

    def channel(self, channel):
        """Select Channel: 1 or 2"""
        self.write('CHN ' + str(channel))
        #be carefull needs space between CHN and channel. Same everywhere

    def output(self, output):
        """Turn ON or OFF the output of selected channel:
            
            type 'ON' or 1 to turn on
            
            type 'OFF' or 0 to turn off
        """
        if output == 1:
            self.write('OUTPUT ON')
        elif output == 0:
            self.write('OUTPUT OFF')
        else:
            self.write('OUTPUT ' + output)

    def freq(self, freq):
        """Set signal frequency in Hz"""
        self.write('FREQ ' + str(freq))

    def ampl(self, ampl):
        """Set signal amplitude (Vpp) in VOLTS"""
        self.write('ampl ' + str(ampl))

    def offset(self, offset):
        """Set the signal DC offset in VOLTS"""
        self.write('DCOFFS ' + str(offset))

    def phase(self, phase):
        """Set the waveform phase offset in DEGREES"""
        self.write('PHASE ' + str(phase))

    def align(self, align):
        """Align phase for both channels"""
        self.write('ALIGN')

    def waveform(self, wave):
        """Set the waveform: SINE, SQUARE, TRIANG, PULSE, NOISE, ARB"""
        if wave == 'triangular' or wave == 'Triangular' or wave == 'TRIANGULAR':
            self.write('WAVE TRIANG')
        elif wave == 'arbitrary' or wave == 'Arbitrary' or wave == 'ARBITRARY':
            self.write('WAVE ARB')
        else:
            self.write('WAVE ' + wave)
