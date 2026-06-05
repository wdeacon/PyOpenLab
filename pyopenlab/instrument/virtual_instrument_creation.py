# -*- coding: utf-8 -*-
"""Entry-point script that starts a 32-bit listener for the 64/32-bit bridge.

Run by :func:`pyopenlab.instrument.virtual_instrument.setup_communication` in a
32-bit interpreter. It takes the instrument's module and class name as command
line arguments and starts the listening loop. See ``virtual_instrument`` for
the full mechanism.
"""
import sys

import qtpy

import pyopenlab
from pyopenlab.instrument.virtual_instrument import inialise_listenser

print(sys.argv)
inialise_listenser(sys.argv[1], sys.argv[2])
#python32 virtual_instrument_creation.py "pyopenlab.instrument.camera" "DummyCamera"
