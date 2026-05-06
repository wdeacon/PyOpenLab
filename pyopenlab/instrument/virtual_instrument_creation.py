# -*- coding: utf-8 -*-
"""
Created on Mon Jul 03 09:23:39 2017

@author: wmd22
A scipt for creating the 32 bit listener in the 64-32 control method
"""
import sys

import qtpy

import pyopenlab
from pyopenlab.instrument.virtual_instrument import inialise_listenser

print(sys.argv)
inialise_listenser(sys.argv[1], sys.argv[2])
#python32 virtual_instrument_creation.py "pyopenlab.instrument.camera" "DummyCamera"
