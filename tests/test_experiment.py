"""
Test for the experiment module
==============================

unfortunately, this needs a GUI to test it - so it's not compatible with
automated unit testing (yet...)
"""

import pyopenlab
import pyopenlab.experiment, pyopenlab.instrument
from pyopenlab.experiment import Experiment
from traits.api import Button, Int
from traitsui.api import View, VGroup, Item

class Blinky(pyopenlab.instrument.Instrument):
    status = Int(0)

if __name__ == '__main__':
    b = Blinky()
    b.edit_traits()

    e = Experiment()
    e.configure_traits()

