# -*- coding: utf-8 -*-
"""ctypes driver for the Andor Kymera spectrograph.

Wraps the ATSpectrograph DLL (the successor to the older ShamrockCIF API),
exposing gratings, wavelength, slits, the output flipper mirror and calibration.
A legacy :class:`KymeraLegacy` driver targeting the older Shamrock DLLs is kept
for 32-bit and Windows <10 systems.
"""
from ctypes import *
import os
#TODO: Implement functions for:
# - focus mirror
# - flipper mirror
# - accessoires
# - output slit
# - Shutter
import platform
import sys
import time

import cv2

from pyopenlab.instrument import Instrument
from pyopenlab.ui.ui_tools import *
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import *
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic
from pyopenlab.utils.notified_property import NotifiedProperty


class Kymera(Instrument):
    """Driver for an Andor Kymera spectrograph via the ATSpectrograph DLL."""

    def __init__(self):
        """Load the ATSpectrograph DLL and initialise the device."""
        super(Kymera, self).__init__()
        #for Windows
        architecture = platform.architecture()

        self.dll = CDLL(r"C:\Program Files\Andor SDK\ATSpectrograph\64\atspectrograph.dll")

        error = self.dll.ATSpectrographInitialize("")  #(byref(tekst))
        self.current_kymera = 0  #for more than one kymera this has to be varied, see KymeraGetNumberDevices
        self._logger.setLevel('WARNING')

    def verbose(self, error, function=''):
        """Log a decoded DLL result at info level.

        Args:
            error (str): Human-readable error string (typically from
                ``ERROR_CODE``).
            function (str): Name of the calling DLL wrapper, for context.
        """
        self.log("[%s]: %s" % (function, error), level='info')

    #basic Kymera features
    def Initialize(self):
        """Initialise the ATSpectrograph library."""
        error = self.dll.ATSpectrographInitialize("")
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetNumberDevices(self):
        """Return the number of connected Kymera devices.

        Returns:
            int: Count of detected Kymera spectrographs.
        """
        no_kymeras = c_int()
        error = self.dll.ATSpectrographGetNumberDevices(byref(no_kymeras))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return no_kymeras.value

    num_kymeras = property(GetNumberDevices)

    def Close(self):
        """Close the ATSpectrograph library and release the device."""
        error = self.dll.ATSpectrographClose()
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetSerialNumber(self):
        """Return the device serial number.

        Returns:
            ctypes.c_char: Raw serial-number buffer as populated by the DLL.
        """
        ATSpectrographSN = c_char()
        error = self.dll.ATSpectrographGetSerialNumber(self.current_kymera, byref(ATSpectrographSN))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return ATSpectrographSN

    serial_number = property(GetSerialNumber)

    def EepromGetOpticalParams(self):
        """Read the spectrograph optical parameters from EEPROM.

        Returns:
            dict: Mapping with ``FocalLength``, ``AngularDeviation`` and
            ``FocalTilt`` as ``ctypes.c_float`` values.
        """
        self.FocalLength = c_float()
        self.AngularDeviation = c_float()
        self.FocalTilt = c_float()
        error = self.dll.ATSpectrographEepromGetOpticalParams(self.current_kymera,
                                                              byref(self.FocalLength),
                                                              byref(self.AngularDeviation),
                                                              byref(self.FocalTilt))
        return {
            'FocalLength': self.FocalLength,
            'AngularDeviation': self.AngularDeviation,
            'FocalTilt': self.FocalTilt}

    #basic Grating features
    def GratingIsPresent(self):
        """Return whether a grating is fitted.

        Returns:
            int: Non-zero if a grating is present.

        Note:
            The DLL output ``is_present`` is passed by value rather than by
            reference, so the returned flag may not be populated correctly. Left
            as-is to preserve behaviour.
        """
        is_present = c_int()
        error = self.dll.ATSpectrographGratingIsPresent(self.current_kymera, is_present)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return is_present.value

    grating_present = property(GratingIsPresent)

    def GetTurret(self):
        """Return the current turret index.

        Returns:
            int: Active turret position.
        """
        Turret = c_int()
        error = self.dll.ATSpectrographGetTurret(self.current_kymera, byref(Turret))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return Turret.value

    def SetTurret(self, turret):
        """Select the turret.

        Args:
            turret (int): Turret index to move to.
        """
        error = self.dll.ATSpectrographSetTurret(self.current_kymera, c_int(turret))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    turret_position = NotifiedProperty(GetTurret, SetTurret)

    def GetNumberGratings(self):
        """Return the number of gratings on the active turret.

        Returns:
            ctypes.c_int: Grating count as populated by the DLL.
        """
        self.noGratings = c_int()
        error = self.dll.ATSpectrographGetNumberGratings(self.current_kymera,
                                                         byref(self.noGratings))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return self.noGratings

    num_gratings = property(GetNumberGratings)
    print(num_gratings)

    def GetGrating(self):
        """Return the active grating index.

        Returns:
            int: Currently selected grating.
        """
        grating = c_int()
        error = self.dll.ATSpectrographGetGrating(self.current_kymera, byref(grating))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return grating.value

    def SetGrating(self, grating_num):
        """Select a grating.

        Args:
            grating_num (int): Grating index to move to (coerced to int).
        """
        grating_num = int(grating_num)
        grating = c_int(grating_num)
        error = self.dll.ATSpectrographSetGrating(self.current_kymera, grating)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    current_grating = NotifiedProperty(GetGrating, SetGrating)

    def GetGratingInfo(self):
        """Return descriptive parameters for the active grating.

        Returns:
            list: ``[lines, blaze, home, offset]`` where ``lines`` is the groove
            density, ``blaze`` the blaze label, and ``home``/``offset`` are motor
            step values.
        """
        lines = c_float()
        blaze = c_char()
        home = c_int()
        offset = c_int()
        error = self.dll.ATSpectrographGetGratingInfo(self.current_kymera, self.current_grating,
                                                      byref(lines), byref(blaze), byref(home),
                                                      byref(offset))
        CurrGratingInfo = [lines.value, blaze.value, home.value, offset.value]
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return CurrGratingInfo

    GratingInfo = property(GetGratingInfo)

    def GetGratingOffset(self):
        """Return the active grating's offset in motor steps.

        Returns:
            ctypes.c_int: Grating offset in steps as populated by the DLL.
        """
        GratingOffset = c_int()  #not this is in steps, so int
        error = self.dll.ATSpectrographGetGratingOffset(self.current_kymera, self.current_grating,
                                                        byref(GratingOffset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return GratingOffset

    def SetGratingOffset(self, offset):
        """Set the active grating's offset.

        Args:
            offset (int): Grating offset in motor steps.
        """
        error = self.dll.ATSpectrographSetGratingOffset(self.current_kymera, self.current_grating,
                                                        c_int(offset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    Grating_offset = NotifiedProperty(GetGratingOffset, SetGratingOffset)

    def GetDetectorOffset(self):
        """Return the detector offset in motor steps.

        Returns:
            int: Detector offset in steps.
        """
        DetectorOffset = c_int()  #note this is in steps, so int
        #error = self.dll.ShamrockGetDetectorOffset(self.current_kymera,byref(self.DetectorOffset))
        error = self.dll.ATSpectrographGetDetectorOffset(self.current_kymera, byref(DetectorOffset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return DetectorOffset.value

    def SetDetectorOffset(self, offset):
        """Set the detector offset.

        Args:
            offset (int): Detector offset in motor steps.
        """
        error = self.dll.ATSpectrographSetDetectorOffset(self.current_kymera, self.current_grating,
                                                         c_int(offset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    detector_offset = NotifiedProperty(GetDetectorOffset, SetDetectorOffset)

    #Wavelength features
    def WavelengthIsPresent(self):
        """Return whether the wavelength drive motor is present.

        Returns:
            int: Non-zero if the wavelength motor is fitted.
        """
        ispresent = c_int()
        error = self.dll.ATSpectrographWavelengthIsPresent(self.current_kymera, byref(ispresent))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return ispresent.value

    motor_present = property(WavelengthIsPresent)

    def GetWavelength(self):
        """Return the current centre wavelength.

        Returns:
            float: Centre wavelength in nm.
        """
        curr_wave = c_float()
        error = self.dll.ATSpectrographGetWavelength(self.current_kymera, byref(curr_wave))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return curr_wave.value

    def SetWavelength(self, centre_wl):
        """Move the grating to a centre wavelength.

        Args:
            centre_wl (float): Target centre wavelength in nm.
        """
        error = self.dll.ATSpectrographSetWavelength(self.current_kymera, c_float(centre_wl))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    center_wavelength = NotifiedProperty(GetWavelength, SetWavelength)

    def AtZeroOrder(self):
        """Return whether the grating is at zero order.

        Returns:
            int: Non-zero if positioned at zero order.
        """
        is_at_zero = c_int()
        error = self.dll.ATSpectrographAtZeroOrder(self.current_kymera, byref(is_at_zero))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return is_at_zero.value

    wavelength_is_zero = property(AtZeroOrder)

    def GetWavelengthLimits(self):
        """Return the accessible wavelength range for the active grating.

        Returns:
            list: ``[min_wl, max_wl]`` in nm.
        """
        min_wl = c_float()
        max_wl = c_float()
        error = self.dll.ATSpectrographGetWavelengthLimits(self.current_kymera,
                                                           self.current_grating, byref(min_wl),
                                                           byref(max_wl))
        wl_limits = [min_wl.value, max_wl.value]
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return wl_limits

    wavelength_limits = property(GetWavelengthLimits)

    def GotoZeroOrder(self):
        """Drive the grating to zero order."""
        error = self.dll.ATSpectrographGotoZeroOrder(self.current_kymera)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #Slit functions
    def AutoSlitIsPresent(self):
        """Return which motorised slits are fitted.

        Returns:
            list[int]: Presence flag for each of the four slit indices (1-4).
        """
        present = c_int()
        slits = []

        for i in range(1, 5):
            self.dll.ATSpectrographAutoSlitIsPresent(self.current_kymera, i, present)
            slits.append(present.value)
        return slits

    Autoslits = property(AutoSlitIsPresent)

    #Sets the slit to the default value (10um)
    def AutoSlitReset(self, slit):
        """Reset a motorised slit to its default 10 um width.

        Args:
            slit (int): Slit index to reset.

        Note:
            The DLL call uses ``self.current_slit`` (which is never defined on
            this class) instead of the ``slit`` argument, so this raises
            AttributeError. Logged and left unchanged.
        """
        error = self.dll.ATSpectrographAutoSlitReset(self.current_kymera, self.current_slit)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #finds if input slit is present
    def SlitIsPresent(self):
        """Return whether the input slit is fitted.

        Returns:
            int: Non-zero if the input slit is present.
        """
        slit_present = c_int()
        error = self.dll.ATSpectrographSlitIsPresent(self.current_kymera, byref(slit_present))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slit_present.value

    slit_present = property(SlitIsPresent)

    #Output Slits
    def GetAutoSlitWidth(self, slit):
        """Return the width of a motorised slit.

        Args:
            slit (int): Slit index to query.

        Returns:
            float: Slit width in microns.
        """
        slitw = c_float()
        error = self.dll.ATSpectrographGetAutoSlitWidth(self.current_kymera, slit, byref(slitw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slitw.value

    def SetAutoSlitWidth(self, slit, width):
        """Set the width of a motorised slit.

        Args:
            slit (int): Slit index to set.
            width (float): Target slit width in microns.

        Returns:
            float: The requested ``width``.

        Note:
            The DLL call omits the ``slit`` index argument (passing only the
            width), so the wrong slit may be addressed. Logged and left
            unchanged.
        """
        slit_w = c_float(width)
        error = self.dll.ATSpectrographSetAutoSlitWidth(self.current_kymera, slit_w)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return width

    #Input Slits
    def GetSlit(self):
        """Return the input slit width.

        Returns:
            float: Input slit width in microns.
        """
        slitw = c_float()
        error = self.dll.ATSpectrographGetSlitWidth(self.current_kymera, c_ulong(1), byref(slitw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slitw.value

    def SetSlit(self, width):
        """Set the input slit width.

        Args:
            width (float): Target slit width in microns.
        """
        slit_w = c_float(width)
        error = self.dll.ATSpectrographSetSlitWidth(self.current_kymera, c_ulong(1), slit_w)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    slit_width = NotifiedProperty(GetSlit, SetSlit)

    def SlitReset(self):
        """Reset the input slit to its default width."""
        error = self.dll.ATSpectrographSlitReset(self.current_kymera)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #Output Flipper Mirror functions
    def FlipperMirrorIsPresent(self):
        """Return whether the output flipper mirror is fitted.

        Returns:
            int: Non-zero if the flipper mirror is present.
        """
        flipper_present = c_int()
        error = self.dll.ATSpectrographFlipperMirrorIsPresent(self.current_kymera, c_ulong(2),
                                                              byref(flipper_present))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return flipper_present.value

    flipper_present = property(FlipperMirrorIsPresent)

    def FlipperMirrorReset(self):
        """Reset the output flipper mirror to its default position."""
        error = self.dll.ATSpectrographFlipperMirrorReset(self.current_kymera, c_ulong(2))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetFlipperMirror(self):
        """Return the active output port via the flipper mirror.

        Returns:
            int: Output port number (1-based; see :meth:`SetFlipperMirror`).
        """
        flipper_position = c_int()
        error = self.dll.ATSpectrographGetFlipperMirror(self.current_kymera, c_ulong(2),
                                                        byref(flipper_position))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return flipper_position.value + 1

    def SetFlipperMirror(self, out_port_nr):
        """Select the output port via the flipper mirror.

        Args:
            out_port_nr (int): Output port to select; 1 is the direct port
                (usually into the CCD) and 2 is the side port (used when the
                flipper mirror is slotted in). Converted to the 0-based value the
                DLL expects.
        """
        out_port_nr = int(out_port_nr - 1)
        out_port = c_int(out_port_nr)
        error = self.dll.ATSpectrographSetFlipperMirror(self.current_kymera, c_ulong(2), out_port)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    output_port = NotifiedProperty(GetFlipperMirror, SetFlipperMirror)

    #Calibration functions
    def SetPixelWidth(self, width):
        """Set the detector pixel width used for calibration.

        Args:
            width (float): Pixel width in microns.
        """
        error = self.dll.ATSpectrographSetPixelWidth(self.current_kymera, c_float(width))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetPixelWidth(self):
        """Return the configured detector pixel width.

        Returns:
            float: Pixel width in microns.
        """
        pixelw = c_float()
        error = self.dll.ATSpectrographGetPixelWidth(self.current_kymera, byref(pixelw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return pixelw.value

    pixel_width = NotifiedProperty(GetPixelWidth, SetPixelWidth)

    def GetNumberPixels(self):
        """Return the configured detector pixel count.

        Returns:
            int: Number of pixels along the dispersion axis.
        """
        numpix = c_int()
        error = self.dll.ATSpectrographGetNumberPixels(self.current_kymera, byref(numpix))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return numpix.value

    def SetNumberPixels(self, pixels):
        """Set the detector pixel count used for calibration.

        Args:
            pixels (int): Number of detector pixels along the dispersion axis.
        """
        error = self.dll.ATSpectrographSetNumberPixels(self.current_kymera, pixels)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    pixel_number = NotifiedProperty(GetNumberPixels, SetNumberPixels)

    def GetCalibration(self):
        """Return the per-pixel wavelength calibration.

        Returns:
            list[float]: Wavelength (nm) for each detector pixel.
        """
        ccalib = c_float * self.pixel_number
        ccalib_array = ccalib()
        error = self.dll.ATSpectrographGetCalibration(self.current_kymera, pointer(ccalib_array),
                                                      self.pixel_number)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        calib = []
        for i in range(len(ccalib_array)):
            calib.append(ccalib_array[i])
        return calib[:]

    wl_calibration = property(GetCalibration)

    def GetPixelCalibrationCoefficients(self):
        """Return the polynomial pixel-to-wavelength calibration coefficients.

        Returns:
            list: ``[ca, cb, cc, cd]`` as ``ctypes.c_float`` polynomial
            coefficients.
        """
        ca = c_float()
        cb = c_float()
        cc = c_float()
        cd = c_float()
        error = self.dll.ATSpectrographGetPixelCalibrationCoefficients(
            self.current_kymera, byref(ca), byref(cb), byref(cc), byref(cd))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return [ca, cb, cc, cd]

    PixelCalibrationCoefficients = property(GetPixelCalibrationCoefficients)

    def get_qt_ui(self):
        """Return a Qt control widget for this spectrograph.

        Returns:
            KymeraControlUI: A new control widget bound to this instance.
        """
        return KymeraControlUI(self)


ERROR_CODE = {
    20201: "ATSPECTROGRAPH_COMMUNICATION_ERROR",
    20202: "ATSPECTROGRAPH_SUCCESS",
    20266: "ATSPECTROGRAPH_P1INVALID",
    20267: "ATSPECTROGRAPH_P2INVALID",
    20268: "ATSPECTROGRAPH_P3INVALID",
    20269: "ATSPECTROGRAPH_P4INVALID",
    20270: "ATSPECTROGRAPH_P5INVALID",
    20275: "ATSPECTROGRAPH_NOT_INITIALIZED",
    20249: "ERROR"}


class KymeraLegacy(Instrument):
    """Legacy Kymera driver for the older Shamrock DLLs (32-bit, Windows <10).

    Note:
        ``__init__`` calls ``super(Kymera, self).__init__()`` rather than
        ``super(KymeraLegacy, self)``. Because ``KymeraLegacy`` is not a subclass
        of ``Kymera`` this raises TypeError on instantiation. Logged and left
        unchanged.
    """

    def __init__(self):
        """Load the architecture-specific Shamrock DLLs and initialise."""
        super(Kymera, self).__init__()
        #for Windows
        architecture = platform.architecture()

        if architecture[0] == "64bit":
            self.dll2 = CDLL("C:\\Program Files\\Andor SDK\\Shamrock64\\atshamrock"
                             )  #"C:\\Program Files\\Andor SOLIS\\Drivers\\Shamrock64\\atshamrock")
            self.dll = CDLL("C:\\Program Files\\Andor SDK\\Shamrock64\\ShamrockCif"
                            )  #C:\\Program Files\\Andor SOLIS\\Drivers\\Shamrock64\\ShamrockCIF")
            tekst = c_char()
            error = self.dll.ShamrockInitialize(byref(tekst))

        elif architecture[0] == "32bit":
            self.dll2 = WinDLL("C:\\Program Files\\Andor SDK\\Shamrock\\atshamrock.dll")
            self.dll = WinDLL("C:\\Program Files\\Andor SDK\\Shamrock\\ShamrockCIF.dll")
            tekst = c_char_p("")
            error = self.dll.ShamrockInitialize(tekst)

        self.current_shamrock = 0  #for more than one Shamrock this has to be varied, see ShamrockGetNumberDevices
        self.center_wavelength = 0.0

    def verbose(self, error, function=''):
        """Log a decoded DLL result at info level."""
        self.log("[%s]: %s" % (function, error), level='info')

    #basic Shamrock features
    def Initialize(self):
        """Initialise the Shamrock library."""
        error = self.dll.ShamrockInitialize("")
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetNumberDevices(self):
        """Return the number of connected Shamrock devices."""
        no_shamrocks = c_int()
        error = self.dll.ShamrockGetNumberDevices(byref(no_shamrocks))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return no_shamrocks.value

    num_shamrocks = property(GetNumberDevices)

    def Close(self):
        """Close the Shamrock library and release the device."""
        error = self.dll.ShamrockClose()
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetSerialNumber(self):
        """Return the device serial number as a raw ctypes buffer."""
        ShamrockSN = c_char()
        error = self.dll.ShamrockGetSerialNumber(self.current_shamrock, byref(ShamrockSN))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return ShamrockSN

    serial_number = property(GetSerialNumber)

    def EepromGetOpticalParams(self):
        """Read optical parameters from EEPROM as a dict of c_float values."""
        self.FocalLength = c_float()
        self.AngularDeviation = c_float()
        self.FocalTilt = c_float()
        error = self.dll.ShamrockEepromGetOpticalParams(self.current_shamrock,
                                                        byref(self.FocalLength),
                                                        byref(self.AngularDeviation),
                                                        byref(self.FocalTilt))
        return {
            'FocalLength': self.FocalLength,
            'AngularDeviation': self.AngularDeviation,
            'FocalTilt': self.FocalTilt}

    #basic Grating features
    def GratingIsPresent(self):
        """Return whether a grating is fitted (non-zero if present)."""
        is_present = c_int()
        error = self.dll.ShamrockGratingIsPresent(self.current_shamrock, is_present)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return is_present.value

    grating_present = property(GratingIsPresent)

    def GetTurret(self):
        """Return the current turret index."""
        Turret = c_int()
        error = self.dll.ShamrockGetTurret(self.current_shamrock, byref(Turret))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return Turret.value

    def SetTurret(self, turret):
        """Select the turret given by index ``turret``."""
        error = self.dll.ShamrockSetTurret(self.current_shamrock, c_int(turret))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    turret_position = NotifiedProperty(GetTurret, SetTurret)

    def GetNumberGratings(self):
        """Return the number of gratings as a c_int."""
        self.noGratings = c_int()
        error = self.dll.ShamrockGetNumberGratings(self.current_shamrock, byref(self.noGratings))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return self.noGratings

    num_gratings = property(GetNumberGratings)

    def GetGrating(self):
        """Return the active grating index."""
        grating = c_int()
        error = self.dll.ShamrockGetGrating(self.current_shamrock, byref(grating))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return grating.value

    def SetGrating(self, grating_num):
        """Select grating ``grating_num`` (coerced to int)."""
        grating_num = int(grating_num)
        grating = c_int(grating_num)
        error = self.dll.ShamrockSetGrating(self.current_shamrock, grating)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    current_grating = NotifiedProperty(GetGrating, SetGrating)

    def GetGratingInfo(self):
        """Return ``[lines, blaze, home, offset]`` for the active grating."""
        lines = c_float()
        blaze = c_char()
        home = c_int()
        offset = c_int()
        error = self.dll.ShamrockGetGratingInfo(self.current_shamrock, self.current_grating,
                                                byref(lines), byref(blaze), byref(home),
                                                byref(offset))
        CurrGratingInfo = [lines.value, blaze.value, home.value, offset.value]
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return CurrGratingInfo

    GratingInfo = property(GetGratingInfo)

    def GetGratingOffset(self):
        """Return the active grating's offset (steps) as a c_int."""
        GratingOffset = c_int()  #not this is in steps, so int
        error = self.dll.ShamrockGetGratingOffset(self.current_shamrock, self.current_grating,
                                                  byref(GratingOffset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return GratingOffset

    def SetGratingOffset(self, offset):
        """Set the active grating's offset to ``offset`` motor steps."""
        error = self.dll.ShamrockSetGratingOffset(self.current_shamrock, self.current_grating,
                                                  c_int(offset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    Grating_offset = NotifiedProperty(GetGratingOffset, SetGratingOffset)

    def GetDetectorOffset(self):
        """Return the detector offset in motor steps."""
        DetectorOffset = c_int()  #note this is in steps, so int
        #error = self.dll.ShamrockGetDetectorOffset(self.current_shamrock,byref(self.DetectorOffset))
        error = self.dll.ShamrockGetDetectorOffset(self.current_shamrock, byref(DetectorOffset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return DetectorOffset.value

    def SetDetectorOffset(self, offset):
        """Set the detector offset to ``offset`` motor steps."""
        error = self.dll.ShamrockSetDetectorOffset(self.current_shamrock, self.current_grating,
                                                   c_int(offset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    detector_offset = NotifiedProperty(GetDetectorOffset, SetDetectorOffset)

    #Wavelength features
    def WavelengthIsPresent(self):
        """Return whether the wavelength drive motor is fitted."""
        ispresent = c_int()
        error = self.dll.ShamrockWavelengthIsPresent(self.current_shamrock, byref(ispresent))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return ispresent.value

    motor_present = property(WavelengthIsPresent)

    def GetWavelength(self):
        """Return the current centre wavelength in nm."""
        curr_wave = c_float()
        error = self.dll.ShamrockGetWavelength(self.current_shamrock, byref(curr_wave))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return curr_wave.value

    def SetWavelength(self, centre_wl):
        """Move the grating to centre wavelength ``centre_wl`` (nm)."""
        error = self.dll.ShamrockSetWavelength(self.current_shamrock, c_float(centre_wl))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    center_wavelength = NotifiedProperty(GetWavelength, SetWavelength)

    def AtZeroOrder(self):
        """Return whether the grating is at zero order."""
        is_at_zero = c_int()
        error = self.dll.ShamrockAtZeroOrder(self.current_shamrock, byref(is_at_zero))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return is_at_zero.value

    wavelength_is_zero = property(AtZeroOrder)

    def GetWavelengthLimits(self):
        """Return ``[min_wl, max_wl]`` (nm) for the active grating."""
        min_wl = c_float()
        max_wl = c_float()
        error = self.dll.ShamrockGetWavelengthLimits(self.current_shamrock, self.current_grating,
                                                     byref(min_wl), byref(max_wl))
        wl_limits = [min_wl.value, max_wl.value]
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return wl_limits

    wavelength_limits = property(GetWavelengthLimits)

    def GotoZeroOrder(self):
        """Drive the grating to zero order."""
        error = self.dll.ShamrockGotoZeroOrder(self.current_shamrock)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #Slit functions
    def AutoSlitIsPresent(self):
        """Return a presence flag for each of the four motorised slits."""
        present = c_int()
        slits = []

        for i in range(1, 5):
            self.dll.ShamrockAutoSlitIsPresent(self.current_shamrock, i, present)
            slits.append(present.value)
        return slits

    Autoslits = property(AutoSlitIsPresent)

    #Sets the slit to the default value (10um)
    def AutoSlitReset(self, slit):
        """Reset a motorised slit to its default 10 um width.

        Note:
            Uses ``self.current_slit`` (never defined) instead of ``slit``, so
            this raises AttributeError. Logged and left unchanged.
        """
        error = self.dll.ShamrockAutoSlitReset(self.current_shamrock, self.current_slit)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #finds if input slit is present
    def SlitIsPresent(self):
        """Return whether the input slit is fitted."""
        slit_present = c_int()
        error = self.dll.ShamrockSlitIsPresent(self.current_shamrock, byref(slit_present))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slit_present.value

    slit_present = property(SlitIsPresent)

    #Output Slits
    def GetAutoSlitWidth(self, slit):
        """Return the width (microns) of motorised slit ``slit``."""
        slitw = c_float()
        error = self.dll.ShamrockGetAutoSlitWidth(self.current_shamrock, slit, byref(slitw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slitw.value

    def SetAutoSlitWidth(self, slit, width):
        """Set motorised slit ``slit`` to ``width`` microns; return ``width``."""
        slit_w = c_float(width)
        error = self.dll.ShamrockSetAutoSlitWidth(self.current_shamrock, slit, slit_w)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return width

    #Input Slits
    def GetSlit(self):
        """Return the input slit width in microns."""
        slitw = c_float()
        error = self.dll.ShamrockGetSlit(self.current_shamrock, byref(slitw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slitw.value

    def SetSlit(self, width):
        """Set the input slit to ``width`` microns."""
        slit_w = c_float(width)
        error = self.dll.ShamrockSetSlit(self.current_shamrock, slit_w)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    slit_width = NotifiedProperty(GetSlit, SetSlit)

    def SlitReset(self):
        """Reset the input slit to its default width."""
        error = self.dll.ShamrockSlitReset(self.current_shamrock)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #Calibration functions
    def SetPixelWidth(self, width):
        """Set the detector pixel width to ``width`` microns."""
        error = self.dll.ShamrockSetPixelWidth(self.current_shamrock, c_float(width))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetPixelWidth(self):
        """Return the configured detector pixel width in microns."""
        pixelw = c_float()
        error = self.dll.ShamrockGetPixelWidth(self.current_shamrock, byref(pixelw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return pixelw.value

    pixel_width = NotifiedProperty(GetPixelWidth, SetPixelWidth)

    def GetNumberPixels(self):
        """Return the configured detector pixel count."""
        numpix = c_int()
        error = self.dll.ShamrockGetNumberPixels(self.current_shamrock, byref(numpix))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return numpix.value

    def SetNumberPixels(self, pixels):
        """Set the detector pixel count to ``pixels``."""
        error = self.dll.ShamrockSetNumberPixels(self.current_shamrock, pixels)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    pixel_number = NotifiedProperty(GetNumberPixels, SetNumberPixels)

    def GetCalibration(self):
        """Return the per-pixel wavelength calibration as a list of floats."""
        ccalib = c_float * self.pixel_number
        ccalib_array = ccalib()
        error = self.dll.ShamrockGetCalibration(self.current_shamrock, pointer(ccalib_array),
                                                self.pixel_number)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        calib = []
        for i in range(len(ccalib_array)):
            calib.append(ccalib_array[i])
        return calib[:]

    wl_calibration = property(GetCalibration)

    def GetPixelCalibrationCoefficients(self):
        """Return polynomial calibration coefficients ``[ca, cb, cc, cd]``."""
        ca = c_float()
        cb = c_float()
        cc = c_float()
        cd = c_float()
        error = self.dll.ShamrockGetPixelCalibrationCoefficients(self.current_shamrock, byref(ca),
                                                                 byref(cb), byref(cc), byref(cd))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return [ca, cb, cc, cd]

    PixelCalibrationCoefficients = property(GetPixelCalibrationCoefficients)

    def get_qt_ui(self):
        """Return a Qt control widget for this spectrograph."""
        return KymeraControlUI(self)


class KymeraControlUI(QtWidgets.QWidget, UiTools):
    """Qt control widget (loaded from a .ui file) for a Kymera spectrograph."""

    def __init__(self,
                 kymera,
                 ui_file=os.path.join(os.path.dirname(__file__), 'kymera_4grating.ui'),
                 parent=None):
        """Load the .ui layout and wire its widgets to a Kymera instance.

        Args:
            kymera (Kymera): The spectrograph to control.
            ui_file (str): Path to the Qt Designer .ui file describing the layout.
            parent: Optional parent Qt widget.
        """
        assert isinstance(kymera, Kymera), "instrument must be a Triax"
        super(KymeraControlUI, self).__init__()
        uic.loadUi(ui_file, self)
        self.kymera = kymera
        self.centre_wl_lineEdit.returnPressed.connect(self.set_wl_gui)
        self.slit_lineEdit.returnPressed.connect(self.set_slit_gui)
        self.centre_wl_lineEdit.setText(str(self.kymera.center_wavelength))
        self.slit_lineEdit.setText(str(self.kymera.slit_width))
        #eval('self.grating_'+str(self.kymera.current_grating)+'_radioButton.setChecked(True)')
        for radio_button in [1, 2, 3, 4]:
            eval('self.grating_' + str(radio_button) +
                 '_radioButton.clicked.connect(self.set_grating_gui)')
        getattr(self, f'grating_{self.kymera.current_grating}_radioButton').setChecked(True)

    def set_wl_gui(self):
        """Push the centre-wavelength text field value to the Kymera."""
        self.kymera.center_wavelength = float(self.centre_wl_lineEdit.text().strip())

    def set_slit_gui(self):
        """Push the slit-width text field value to the Kymera."""
        self.kymera.slit_width = float(self.slit_lineEdit.text().strip())

    def set_grating_gui(self):
        """Set the active grating from the checked radio button.

        Raises:
            ValueError: If the sending widget is not one of the grating radio
                buttons.
        """
        s = self.sender()
        if s is self.grating_1_radioButton:
            self.kymera.current_grating = 1
        elif s is self.grating_2_radioButton:
            self.kymera.current_grating = 2
        elif s is self.grating_3_radioButton:
            self.kymera.current_grating = 3
        elif s is self.grating_4_radioButton:
            self.kymera.current_grating = 4
        else:
            raise ValueError('radio buttons not connected!')


def main():
    """Launch a standalone Kymera control window."""
    app = get_qt_app()
    s = Kymera()
    ui = KymeraControlUI(kymera=s)
    ui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    # main()
    k = Kymera()
    k.GetNumberDevices()  #success

    #k.show_gui()
    #self = k
    #k.SetNumberPixels(1600)
    #k.GetCalibration()

    #if k.GetGrating() not in [1,2,3, 4]:
    #    print('Kymera Grating not defined. Moving to Grating 1')
    #    k.SetGrating(1)
    #k.show_gui(block = False)
    #self = k
    #k.SetNumberPixels(1024)
    #k.GetCalibration()
