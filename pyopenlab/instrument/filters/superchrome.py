# -*- coding: utf-8 -*-
"""Driver for the Fianium SuperChrome tunable filter via its vendor SDK DLL."""

from ctypes import *
import os

from pyopenlab.instrument import Instrument


class SuperChrome(Instrument):
    """Controls a Fianium SuperChrome filter through ``SuperChromeSDK.dll``.

    Attributes:
        dll: The loaded ``SuperChromeSDK.dll`` handle (a ``ctypes`` library).
        wvl (int): Last-commanded centre wavelength, in nm.
        bw (int): Last-commanded bandwidth, in nm.
    """

    def __init__(self):
        """Load the SuperChrome SDK DLL and initialise the filter.

        Note:
            The DLL path is hard-coded to a Cambridge-specific GitHub checkout
            (``C:\\Users\\hera.NP-BROMINE2\\...``). It is the functional load path on the
            original rig, so it is left intact, but it must be edited for other machines.
        """
        self.dll = cdll.LoadLibrary(
            r'C:\Users\hera.NP-BROMINE2\Documents\GitHub\pyopenlab\pyopenlab\instrument\filters' +
            "\\SuperChromeSDK.dll")
        self.init()

    def init(self):
        """Initialise the SDK and move the filter to a default 633 nm / 10 nm setting.

        Note:
            Calls ``self.MoveSyncWaveAndBw``, which is not defined on this class and is
            never exposed by the loaded DLL via ``__getattr__``; this method will raise
            ``AttributeError`` as written.
        """
        self.dll.InitialiseDll(windll.kernel32._handle)
        self.dll.Initialise()
        self.MoveSyncWaveAndBw(633, 10)
        self.wvl = 633
        self.bw = 10

    def MoveWvl(self, centWvl, bwWvl):
        """Move the filter to a centre wavelength and bandwidth.

        Args:
            centWvl (int): Centre wavelength, in nm.
            bwWvl (int): Bandwidth, in nm.

        Note:
            Relies on ``self.MoveSyncWaveAndBw``, which is undefined on this class (see
            :meth:`init`).
        """
        print("Moving")
        self.MoveSyncWaveAndBw(centWvl, bwWvl)
        self.wvl = centWvl
        self.bw = bwWvl
