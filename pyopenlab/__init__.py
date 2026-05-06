"""
pyopenlab
=====
This module contains lots of classes and functions to support the
NanoPhotonics group's lab work.
"""

__author__ = 'alansanders,rwb27'
__all__ = []
__version__ = '0.1-dev'

from pyopenlab.datafile import close_current as close_current_datafile
from pyopenlab.datafile import current as current_datafile
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
from pyopenlab.utils.decorators import inherit_docstring
from pyopenlab.utils.log import log
