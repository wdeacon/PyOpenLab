# -*- coding: utf-8 -*-
"""Driver for the PicoQuant TimeHarp 200 TCSPC card via the ThLib DLL.

Each ``Timeharp_*``/``TimeHarp_*`` method wraps a single ThLib ``TH_*`` call. On a
negative return code (a ThLib error) the wrapper logs the decoded error and shuts the
card down via ``TH_Shutdown``.

Note:
    ``ReadErrorFile`` reads a hardcoded path (``R:\\fo263\\manuals\\...``) for the
    error-code lookup table, so error decoding only works where that share is mounted.

@author: Femi Ojambati (fo263)
"""
from __future__ import print_function

from builtins import str
from ctypes import *
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

from pyopenlab.instrument import Instrument

#from pyopenlab.utils.notified_property import NotifiedProperty
#from pyopenlab.ui.ui_tools import QuickControlBox
#from pyopenlab.utils.gui import QtWidgets


class TimeHarp(Instrument):
    """Instrument wrapper for the PicoQuant TimeHarp 200 TCSPC card.

    Loads the ThLib DLL and exposes thin wrappers around the ``TH_*`` driver calls for
    calibration, CFD/sync configuration, measurement control and histogram readout.

    Attributes:
        timeharp_mode (int): Acquisition mode (0 = standard histogramming, 1 = TTTR).
        BLOCKSIZE (int): Number of histogram bins read back by ``TimeHarp_GetBlock``.
    """

    timeharp_mode = 0  #0=standard histogramming, 1=TTTR
    ctcstatus = 0
    countrate = 0
    BLOCKSIZE = 4096

    def __init__(self):
        """Load the ThLib DLL and initialize the card in the default mode."""
        super(TimeHarp, self).__init__()
        #for Windows
        #self.TH_dll = cdll.LoadLibrary(r'C:\Program Files (x86)\PicoQuant\TH200-THLibv61\Thlib_for_x64\Thlib.dll')
        # self.TH_dll = cdll.LoadLibrary('C:\Program Files\PicoQuant\TH200-THLibv61\ThLib.lib')
        self.TH_dll = windll.LoadLibrary(r'ThLib.dll')

        self.Timeharp_Initialize(self.timeharp_mode)

    def verbose(self, error, function=''):
        """Log an error message tagged with the originating function name.

        Args:
            error: The decoded error string to log.
            function: Name of the function that produced the error.
        """
        self.log("[%s]: %s" % (function, error), level='info')

    def Timeharp_Initialize(self, timeharp_mode):
        """Initialize the card in the given mode; shut down on a ThLib error.

        Args:
            timeharp_mode: Acquisition mode (0 = standard histogramming, 1 = TTTR).
        """
        retint = self.TH_dll.TH_Initialize(timeharp_mode)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_Calibrate(self):
        """Calibrate the card; shut down on a ThLib error."""
        retint = self.TH_dll.TH_Calibrate()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_SetCFDDiscrMin(self, CFDLevel=20):
        """Set the CFD discriminator minimum level; shut down on a ThLib error.

        Args:
            CFDLevel: CFD discriminator level in mV.
        """
        retint = self.TH_dll.TH_SetCFDDiscrMin(CFDLevel)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_SetCFDZeroX(self, CFDZeroX=20):
        """Set the CFD zero-cross level; shut down on a ThLib error.

        Args:
            CFDZeroX: CFD zero-cross level in mV.
        """
        retint = self.TH_dll.TH_SetCFDZeroCross(CFDZeroX)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_SetSyncLevel(self, SyncLevel=-700):
        """Set the sync input trigger level; shut down on a ThLib error.

        Args:
            SyncLevel: Sync trigger level in mV.
        """
        retint = self.TH_dll.TH_SetSyncLevel(SyncLevel)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_SetRange(self, Range=0):
        """Set the measurement range/resolution; shut down on a ThLib error.

        Args:
            Range: Range code; 0 = base resolution, 1 = 2x base resolution, and so on.
        """
        # range code 0 = base resolution, 1 = 2 x base resolution and so on.
        retint = self.TH_dll.TH_SetRange(Range)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_SetOffset(self, Offset=0):
        """Set the measurement time offset; shut down on a ThLib error.

        Args:
            Offset: Offset value passed to ``TH_SetOffset``.
        """
        retint = self.TH_dll.TH_SetOffset(Offset)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_SetStopOverflow(self):
        """Enable stop-on-overflow at the maximum bin count; shut down on a ThLib error."""
        retint = self.TH_dll.TH_SetStopOverflow(1, 65535)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_GetResolution(self):
        """Return the current measurement resolution; shut down on a ThLib error.

        Returns:
            int: The resolution reported by ``TH_GetResolution`` (in ps).
        """
        retint = self.TH_dll.TH_GetResolution()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()
        return retint

    def TimeHarp_SetSyncMode(self):
        """Enable sync mode; shut down on a ThLib error."""
        retint = self.TH_dll.TH_SetSyncMode()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_GetCountRate(self):
        """Return the current count rate; shut down on a ThLib error.

        Returns:
            int: The count rate reported by ``TH_GetCountRate`` (counts/s).
        """
        retint = self.TH_dll.TH_GetCountRate()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()
        return retint

    def TimeHarp_ClearHistMem(self, TH_block=0):
        """Clear a histogram memory block; shut down on a ThLib error.

        Args:
            TH_block: Index of the histogram block to clear.
        """
        retint = self.TH_dll.TH_ClearHistMem(TH_block)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_GetFlags(self):
        """Query the card status flags; shut down on a ThLib error."""
        retint = self.TH_dll.TH_GetFlags()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_StartMeas(self):
        """Start a measurement; shut down on a ThLib error."""
        retint = self.TH_dll.TH_StartMeas()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_CTCStatus(self):
        """Return the CTC (acquisition timer) status; shut down on a ThLib error.

        Returns:
            int: The CTC status; non-zero indicates the acquisition time has elapsed.
        """
        retint = self.TH_dll.TH_CTCStatus()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()
        return retint

    def TimeHarp_SetMMode(self, mmode=0, tacq=1000):  #acquire for 1s
        """Set the measurement mode and acquisition time; shut down on a ThLib error.

        Args:
            mmode: Measurement mode (0 = one-time histogramming/TTTR, 1 = continuous).
            tacq: Acquisition time in milliseconds.

        Returns:
            int: The return code from ``TH_SetMMode``.
        """
        retint = self.TH_dll.TH_SetMMode(mmode, tacq)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()
        return retint

    def TimeHarp_StopMeas(self):
        """Stop the current measurement; shut down on a ThLib error."""
        retint = self.TH_dll.TH_StopMeas()
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()

    def TimeHarp_ShutDown(self):
        """Shut down the card via ``TH_Shutdown``."""
        self.TH_dll.TH_Shutdown()

    def TimeHarp_GetBlock(self, block=0):
        """Read back one histogram block; shut down on a ThLib error.

        Args:
            block: Index of the histogram block to read.

        Returns:
            tuple: A ``(retarr, retint)`` pair, where ``retarr`` is a ctypes array of
            ``BLOCKSIZE`` 32-bit bin counts and ``retint`` is the total count returned
            by ``TH_GetBlock``.
        """
        retarr_p = c_uint32 * self.BLOCKSIZE
        retarr = retarr_p()
        retint = self.TH_dll.TH_GetBlock(byref(retarr), block)
        if retint < 0:
            self.verbose(self.FindError(retint), sys._getframe().f_code.co_name)
            self.TH_dll.TH_Shutdown()
        return retarr, retint

    def ReadErrorFile(self):
        """Read and tokenize the ThLib error-code lookup table.

        Note:
            The table path is hardcoded to a network share
            (``R:\\fo263\\manuals\\...``); decoding fails where it is not mounted.

        Returns:
            list: The whitespace-split tokens of the error-code file, alternating
            between codes and their descriptions.
        """
        #mypath = r'C:\Program Files (x86)\PicoQuant\TH200-THLibv61'
        mypath = r'R:\fo263\manuals\TimeHarp200_SW_and_DLL_v6_1'

        filename = 'Errcodes_mod_170920.txt'
        myFile = open(mypath + '\\' + filename, 'r')
        filecontent = myFile.read()
        err_code = filecontent.split()
        myFile.close()

        return err_code

    ERROR_CODE = property(ReadErrorFile)
    """list: The tokenized error-code lookup table, read fresh from disk on access."""

    def FindError(self, thiserror):
        """Decode a ThLib error code into its human-readable description.

        Args:
            thiserror: The numeric error code returned by a ``TH_*`` call.

        Returns:
            str: The description token preceding the matching code in the lookup table.

        Raises:
            ValueError: ``thiserror`` is not found in the error-code table.
        """
        error_index = self.ERROR_CODE.index(str(thiserror))
        return self.ERROR_CODE[error_index - 1]


if __name__ == '__main__':
    th = TimeHarp()
    th.TimeHarp_Calibrate()
    Offset = 0
    CFDZeroX = 10
    CFDLevel = 50
    SyncLevel = -700
    Range = 0
    Tacq = 5000
    #acquisition time in milliseconds
    timeharp_mode = 0  #0=standard histogramming, 1=TTTR
    mmode = 0  # mmode = 0 for one-time histogramming and TTTR 1 for continuous mode

    th = TimeHarp()

    th.TimeHarp_Calibrate()
    time.sleep(1)

    th.TimeHarp_SetCFDDiscrMin(CFDLevel)
    th.TimeHarp_SetCFDZeroX(CFDZeroX)
    th.TimeHarp_SetSyncLevel(SyncLevel)
    th.TimeHarp_SetRange(Range)  #range code 0 = base resolution, 1 = 2 x base resolution and so on.
    th.TimeHarp_SetOffset(Offset)

    resoltuion = th.TimeHarp_GetResolution()

    th.TimeHarp_SetSyncMode()
    time.sleep(1)
    syncrate = th.TimeHarp_GetCountRate()

    th.TimeHarp_SetStopOverflow()

    th.TimeHarp_SetMMode(mmode, Tacq)

    th.TimeHarp_ClearHistMem()

    th.TimeHarp_GetFlags()

    time.sleep(1)
    countrate = th.TimeHarp_GetCountRate()

    th.TimeHarp_StartMeas()

    ctcdone = 0
    while ctcdone == 0:
        ctcdone = th.TimeHarp_CTCStatus()

    th.TimeHarp_StopMeas()

    blockcount, total_count = th.TimeHarp_GetBlock(0)

    th.TimeHarp_ShutDown()

    print(('The resolution is ' + str(resoltuion)))
    print(('The Sync Rate is ' + str(syncrate)))
    print(('The Count Rate is ' + str(countrate)))
    print(('The total count is ' + str(total_count)))

    counts = []
    #
    for i in blockcount:
        counts.append(int(i)),

    plt.figure()
    plt.plot(np.linspace(1, th.BLOCKSIZE, th.BLOCKSIZE), counts)

    #np.plot(counts)
    #
    #np.plot(blockcount)

    #class TimeHarpControlUI(QuickControlBox):
    #    '''Control Widget for the Shamrock spectrometer
    #    '''
    #    def __init__(self,TimeHarp):
    #        super(TimeHarpControlUI,self).__init__(title = 'Shamrock')
    #        self.TimeHarp = TimeHarp
    #        self.add_doublespinbox("center_wavelength")
    #        self.add_doublespinbox("slit_width")
    #        self.add_spinbox("turret_position")
    #        self.add_lineedit('GratingInfo')
    #        self.controls['GratingInfo'].setReadOnly(True)
    #        self.auto_connect_by_name(controlled_object = self.TimeHarp)
    #
