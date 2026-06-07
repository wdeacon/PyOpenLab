# -*- coding: utf-8 -*-
"""ctypes driver for the Andor Shamrock spectrograph.

Wraps the vendor ShamrockCIF DLL, exposing gratings, wavelength, slits and
calibration as Python methods and notified properties.
"""
from ctypes import *
#TODO: Implement functions for:
# - focus mirror
# - flipper mirror
# - accessoires
# - output slit
# - Shutter
import platform
import sys
import time

from pyopenlab.instrument import Instrument
from pyopenlab.ui.ui_tools import *
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.gui import *
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.notified_property import NotifiedProperty


class Shamrock(Instrument):
    """Driver for an Andor Shamrock spectrograph via the ShamrockCIF DLL."""

    def __init__(self):
        """Load the architecture-specific DLLs and initialise the device.

        The 64-bit and 32-bit branches load the Shamrock libraries from their
        respective Andor install paths before calling ``ShamrockInitialize``.
        """
        super(Shamrock, self).__init__()
        #for Windows
        architecture = platform.architecture()

        if architecture[0] == "64bit":
            self.dll2 = CDLL("C:\\Program Files\\Andor SOLIS\\Drivers\\Shamrock64\\atshamrock")
            self.dll = CDLL("C:\\Program Files\\Andor SOLIS\\Drivers\\Shamrock64\\ShamrockCIF")
            tekst = c_char()
            error = self.dll.ShamrockInitialize(byref(tekst))

        elif architecture[0] == "32bit":
            self.dll2 = WinDLL("C:\\Program Files\\Andor SDK\\Shamrock\\atshamrock.dll")
            self.dll = WinDLL("C:\\Program Files\\Andor SDK\\Shamrock\\ShamrockCIF.dll")
            tekst = c_char_p("")
            error = self.dll.ShamrockInitialize(tekst)

        self.current_shamrock = 0  #for more than one Shamrock this has to be varied, see ShamrockGetNumberDevices
        self._logger.setLevel('WARN')

    def verbose(self, error, function=''):
        """Log a decoded DLL result at info level.

        Args:
            error (str): Human-readable error string (typically from
                ``ERROR_CODE``).
            function (str): Name of the calling DLL wrapper, for context.
        """
        self.log("[%s]: %s" % (function, error), level='info')

    #basic Shamrock features
    def Initialize(self):
        """Initialise the Shamrock library."""
        error = self.dll.ShamrockInitialize("")
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetNumberDevices(self):
        """Return the number of connected Shamrock devices.

        Returns:
            int: Count of detected Shamrock spectrographs.
        """
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
        """Return the device serial number.

        Returns:
            ctypes.c_char: Raw serial-number buffer as populated by the DLL.
        """
        ShamrockSN = c_char()
        error = self.dll.ShamrockGetSerialNumber(self.current_shamrock, byref(ShamrockSN))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return ShamrockSN

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
        """Return whether a grating is fitted.

        Returns:
            int: Non-zero if a grating is present.

        Note:
            The DLL output ``is_present`` is passed by value rather than by
            reference, so the returned flag may not be populated correctly. Left
            as-is to preserve behaviour.
        """
        is_present = c_int()
        error = self.dll.ShamrockGratingIsPresent(self.current_shamrock, is_present)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return is_present.value

    grating_present = property(GratingIsPresent)

    def GetTurret(self):
        """Return the current turret index.

        Returns:
            int: Active turret position.
        """
        Turret = c_int()
        error = self.dll.ShamrockGetTurret(self.current_shamrock, byref(Turret))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return Turret.value

    def SetTurret(self, turret):
        """Select the turret.

        Args:
            turret (int): Turret index to move to.
        """
        error = self.dll.ShamrockSetTurret(self.current_shamrock, c_int(turret))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    turret_position = NotifiedProperty(GetTurret, SetTurret)

    def GetNumberGratings(self):
        """Return the number of gratings on the active turret.

        Returns:
            ctypes.c_int: Grating count as populated by the DLL.
        """
        self.noGratings = c_int()
        error = self.dll.ShamrockGetNumberGratings(self.current_shamrock, byref(self.noGratings))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return self.noGratings

    num_gratings = property(GetNumberGratings)

    def GetGrating(self):
        """Return the active grating index.

        Returns:
            int: Currently selected grating.
        """
        grating = c_int()
        error = self.dll.ShamrockGetGrating(self.current_shamrock, byref(grating))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return grating.value

    def SetGrating(self, grating_num):
        """Select a grating.

        Args:
            grating_num (int): Grating index to move to (coerced to int).
        """
        grating_num = int(grating_num)
        grating = c_int(grating_num)
        error = self.dll.ShamrockSetGrating(self.current_shamrock, grating)
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
        error = self.dll.ShamrockGetGratingInfo(self.current_shamrock, self.current_grating,
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
        error = self.dll.ShamrockGetGratingOffset(self.current_shamrock, self.current_grating,
                                                  byref(GratingOffset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return GratingOffset

    def SetGratingOffset(self, offset):
        """Set the active grating's offset.

        Args:
            offset (int): Grating offset in motor steps.
        """
        error = self.dll.ShamrockSetGratingOffset(self.current_shamrock, self.current_grating,
                                                  c_int(offset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    Grating_offset = NotifiedProperty(GetGratingOffset, SetGratingOffset)

    def GetDetectorOffset(self):
        """Return the detector offset in motor steps.

        Returns:
            int: Detector offset in steps.
        """
        DetectorOffset = c_int()  #note this is in steps, so int
        #error = self.dll.ShamrockGetDetectorOffset(self.current_shamrock,byref(self.DetectorOffset))
        error = self.dll.ShamrockGetDetectorOffset(self.current_shamrock, byref(DetectorOffset))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return DetectorOffset.value

    def SetDetectorOffset(self, offset):
        """Set the detector offset.

        Args:
            offset (int): Detector offset in motor steps.
        """
        error = self.dll.ShamrockSetDetectorOffset(self.current_shamrock, self.current_grating,
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
        error = self.dll.ShamrockWavelengthIsPresent(self.current_shamrock, byref(ispresent))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return ispresent.value

    motor_present = property(WavelengthIsPresent)

    def GetWavelength(self):
        """Return the current centre wavelength.

        Returns:
            float: Centre wavelength in nm.
        """
        curr_wave = c_float()
        error = self.dll.ShamrockGetWavelength(self.current_shamrock, byref(curr_wave))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return curr_wave.value

    def SetWavelength(self, centre_wl):
        """Move the grating to a centre wavelength.

        Args:
            centre_wl (float): Target centre wavelength in nm.
        """
        error = self.dll.ShamrockSetWavelength(self.current_shamrock, c_float(centre_wl))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    center_wavelength = NotifiedProperty(GetWavelength, SetWavelength)

    def AtZeroOrder(self):
        """Return whether the grating is at zero order.

        Returns:
            int: Non-zero if positioned at zero order.
        """
        is_at_zero = c_int()
        error = self.dll.ShamrockAtZeroOrder(self.current_shamrock, byref(is_at_zero))
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
        """Return which motorised slits are fitted.

        Returns:
            list[int]: Presence flag for each of the four slit indices (1-4).
        """
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

        Args:
            slit (int): Slit index to reset.

        Note:
            The DLL call uses ``self.current_slit`` (which is never defined on
            this class) instead of the ``slit`` argument, so this raises
            AttributeError. Logged and left unchanged.
        """
        error = self.dll.ShamrockAutoSlitReset(self.current_shamrock, self.current_slit)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    #finds if input slit is present
    def SlitIsPresent(self):
        """Return whether the input slit is fitted.

        Returns:
            int: Non-zero if the input slit is present.
        """
        slit_present = c_int()
        error = self.dll.ShamrockSlitIsPresent(self.current_shamrock, byref(slit_present))
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
        error = self.dll.ShamrockGetAutoSlitWidth(self.current_shamrock, slit, byref(slitw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slitw.value

    def SetAutoSlitWidth(self, slit, width):
        """Set the width of a motorised slit.

        Args:
            slit (int): Slit index to set.
            width (float): Target slit width in microns.

        Returns:
            float: The requested ``width``.
        """
        slit_w = c_float(width)
        error = self.dll.ShamrockSetAutoSlitWidth(self.current_shamrock, slit, slit_w)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return width

    #Input Slits
    def GetSlit(self):
        """Return the input slit width.

        Returns:
            float: Input slit width in microns.
        """
        slitw = c_float()
        error = self.dll.ShamrockGetSlit(self.current_shamrock, byref(slitw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return slitw.value

    def SetSlit(self, width):
        """Set the input slit width.

        Args:
            width (float): Target slit width in microns.
        """
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
        """Set the detector pixel width used for calibration.

        Args:
            width (float): Pixel width in microns.
        """
        error = self.dll.ShamrockSetPixelWidth(self.current_shamrock, c_float(width))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    def GetPixelWidth(self):
        """Return the configured detector pixel width.

        Returns:
            float: Pixel width in microns.
        """
        pixelw = c_float()
        error = self.dll.ShamrockGetPixelWidth(self.current_shamrock, byref(pixelw))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return pixelw.value

    pixel_width = NotifiedProperty(GetPixelWidth, SetPixelWidth)

    def GetNumberPixels(self):
        """Return the configured detector pixel count.

        Returns:
            int: Number of pixels along the dispersion axis.
        """
        numpix = c_int()
        error = self.dll.ShamrockGetNumberPixels(self.current_shamrock, byref(numpix))
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)
        return numpix.value

    def SetNumberPixels(self, pixels):
        """Set the detector pixel count used for calibration.

        Args:
            pixels (int): Number of detector pixels along the dispersion axis.
        """
        error = self.dll.ShamrockSetNumberPixels(self.current_shamrock, pixels)
        self.verbose(ERROR_CODE[error], sys._getframe().f_code.co_name)

    pixel_number = NotifiedProperty(GetNumberPixels, SetNumberPixels)

    def GetCalibration(self):
        """Return the per-pixel wavelength calibration.

        Returns:
            list[float]: Wavelength (nm) for each detector pixel.
        """
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
        """Return the polynomial pixel-to-wavelength calibration coefficients.

        Returns:
            list: ``[ca, cb, cc, cd]`` as ``ctypes.c_float`` polynomial
            coefficients.
        """
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
        """Return a Qt control widget for this spectrograph.

        Returns:
            ShamrockControlUI: A new control widget bound to this instance.
        """
        return ShamrockControlUI(self)


ERROR_CODE = {
    20201: "SHAMROCK_COMMUNICATION_ERROR",
    20202: "SHAMROCK_SUCCESS",
    20266: "SHAMROCK_P1INVALID",
    20267: "SHAMROCK_P2INVALID",
    20268: "SHAMROCK_P3INVALID",
    20269: "SHAMROCK_P4INVALID",
    20270: "SHAMROCK_P5INVALID",
    20275: "SHAMROCK_NOT_INITIALIZED"}


class ShamrockControlUI(QuickControlBox):
    """Control widget for the Shamrock spectrometer."""

    def __init__(self, shamrock):
        """Build the control box and wire it to a Shamrock instance.

        Args:
            shamrock (Shamrock): The spectrograph to control.
        """
        super(ShamrockControlUI, self).__init__(title='Shamrock')
        self.shamrock = shamrock
        self.add_doublespinbox("center_wavelength")
        self.add_doublespinbox("slit_width")
        self.add_spinbox("current_grating")
        self.add_lineedit('GratingInfo')
        self.controls['GratingInfo'].setReadOnly(True)
        self.auto_connect_by_name(controlled_object=self.shamrock)


def main():
    """Launch a standalone Shamrock control window."""
    app = get_qt_app()
    s = Shamrock()
    ui = ShamrockControlUI(shamrock=s)
    ui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    # main()
    s = Shamrock()
    s.show_gui(block=False)
