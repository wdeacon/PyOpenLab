"""Base driver for the Jobin-Yvon Triax spectrometer.

This module provides the :class:`Triax` VISA instrument class and its Qt UI. The
class is intended to be wrapped per-lab because the wavelength calibration
differs between setups.
"""

import os
import time

import numpy as np
import scipy.optimize as spo

from pyopenlab.instrument.visa_instrument import VisaInstrument
from pyopenlab.ui.ui_tools import UiTools
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic


class Triax(VisaInstrument):
    """VISA driver for the Triax spectrometer with per-grating wavelength calibration."""

    metadata_property_names = ('wavelength',)

    def __init__(self, Address, Calibration_Data=[], CCD_Horizontal_Resolution=2000):
        """Open communication with the Triax and build the calibration model.

        To calculate the wavelengths hitting each pixel an inverse process is used: the grating
        stepper-motor position required to place a given wavelength on a given pixel is
        approximated, and a quadratic curve is fitted so that the motor position implied for each
        wavelength/pixel is as close as possible to the real stepper-motor position.

        Args:
            Address: VISA resource address of the Triax connection.
            Calibration_Data: Per-grating calibration. Each entry is a list whose first element is
                the list of calibration wavelengths (ascending) and whose remaining three elements
                are the measured values of each quadratic coefficient at those wavelengths. Pass an
                empty list for a grating to disable calibration (the raw pixel array is returned for
                it).
            CCD_Horizontal_Resolution: Horizontal size, in pixels, of the camera used with the
                Triax.

        Raises:
            Exception: If communication with the Triax cannot be established.
        """

        #--------Attempt to open communication------------

        try:

            VisaInstrument.__init__(self,
                                    Address,
                                    settings=dict(timeout=4000, write_termination='\n'))
            Attempts = 0
            End = False
            while End is False:
                if self.query(" ") == 'F':
                    End = True
                else:
                    self.instr.write_raw(
                        '\x4f\x32\x30\x30\x30\x00')  #Move from boot program to main program
                    time.sleep(2)
                    Attempts += 1
                    if Attempts == 5:
                        raise Exception('Triax communication error!')

        except:
            raise Exception('Triax communication error!')

        #----Generate initial 3x3 calibration arrays for the gratings used for initial estimate of wavelengths on each CCD pixel--------

        self.Grating_Number = self.Grating()  #Current grating number
        self.Calibration_Arrays = []
        for i in Calibration_Data:
            self.Calibration_Arrays.append([])
            if len(i) == 4:
                for j in i[1:]:
                    self.Calibration_Arrays[-1].append(np.polyfit(i[0], j, 2))

        #---------Generate the quadratic fit data to create quadratic splines for the 3x3 calibration arrays for the gratings, used to improve wavelength estimation-----------

        self.Spline_Data = []
        for i in Calibration_Data:
            self.Spline_Data.append([])
            if len(i) == 4:
                self.Spline_Data[-1].append(i[0])
                for j in i[1:]:
                    self.Spline_Data[-1].append([])
                    for k in range(len(self.Spline_Data[-1][0]))[1:-1]:
                        self.Spline_Data[-1][-1].append(
                            np.polyfit(self.Spline_Data[-1][0][k - 1:k + 2], j[k - 1:k + 2], 2))

        #---print regions each grating is calibrated over

        self.Regions = []

        print('This Triax spectrometer is calibrated for use over the following ranges:')
        for i in range(len(Calibration_Data)):
            if len(Calibration_Data[i]) == 4:
                print('Grating', i, ':', np.min(Calibration_Data[i][0]), 'nm - ',
                      np.max(Calibration_Data[i][0]), 'nm')
                self.Regions.append([
                    np.min(Calibration_Data[i][0]),
                    np.max(Calibration_Data[i][0])])
            else:
                self.Regions.append(None)

        self.Wavelength_Array = None  #Not intially set. Updated with a change of grating or stepper motor position
        self.Number_of_Pixels = CCD_Horizontal_Resolution

    def Get_Wavelength_Array(self):
        """Return the cached wavelength array, computing it from the pixel range if not yet set.

        Returns:
            numpy.ndarray: The wavelength (nm) assigned to each CCD pixel.
        """
        if self.Wavelength_Array is None:
            self.Wavelength_Array = self.Convert_Pixels_to_Wavelengths(
                np.array(list(range(self.Number_of_Pixels))))
        return self.Wavelength_Array

    def Grating(self, Set_To=None):
        """Query or set the active grating.

        Args:
            Set_To: ``None`` to query, or ``0``, ``1`` or ``2`` to rotate to that grating position.

        Returns:
            int or None: The current grating number when querying; ``None`` when setting.

        Raises:
            ValueError: If ``Set_To`` is not one of ``None``, ``0``, ``1`` or ``2``.
        """

        #-----Check Input-------

        if Set_To not in [None, 0, 1, 2]:
            raise ValueError('Invalid input for grating input. Must be None, 0, 1, or 2.')

        #----Return current grating or switch grating---------

        if Set_To is None:
            return int(self.query("Z452,0,0,0\r")[1:])

        else:
            self.write("Z451,0,0,0,%i\r" % (Set_To))
            time.sleep(1)
            self.waitTillReady()
            self.Grating_Number = Set_To
            #try:
            self.Wavelength_Array = self.Convert_Pixels_to_Wavelengths(
                np.arange(self.Number_of_Pixels))  #Update wavelength array
            #except:
            #Dump=1

    def Motor_Steps(self):
        """Return the current grating rotation in internal stepper-motor steps.

        Returns:
            int: The current stepper-motor position.
        """

        self.write("H0\r")
        return int(self.read()[1:])

    def Convert_Pixels_to_Wavelengths(self, Pixel_Array):
        """Convert pixel indices to wavelengths for the current grating and position.

        Wavelengths are optimised so that the motor position they imply matches the current
        stepper-motor position; the result is always a quadratic approximation. If the current
        grating has no calibration, ``Pixel_Array`` is returned unchanged.

        Args:
            Pixel_Array: Array of CCD pixel indices to convert.

        Returns:
            numpy.ndarray: Wavelength (nm) per input pixel (or ``Pixel_Array`` if uncalibrated).
        """

        Steps = self.Motor_Steps()  #Check grating position

        if self.Grating_Number <= len(self.Calibration_Arrays):  #Check calibration exists
            if len(self.Calibration_Arrays) == 0 or len(
                    self.Calibration_Arrays[self.Grating_Number]) == 0:
                return Pixel_Array

        Sample_Pixels = np.linspace(np.min(Pixel_Array), np.max(Pixel_Array),
                                    10)  #Make some estimates to the nearest 0.1nm
        Sample_Wavelengths = [np.mean(self.Regions[self.Grating_Number])]
        while len(Sample_Wavelengths) < len(Sample_Pixels):
            Sample_Wavelengths.append(Sample_Wavelengths[0])
        Range = 0.5 * (self.Regions[self.Grating_Number][1] - self.Regions[self.Grating_Number][0])
        Spacing = [10., 1., 0.1]

        while len(Spacing) > 0:
            for i in range(len(Sample_Pixels)):
                To_Test = np.arange(Sample_Wavelengths[i] - Range, Sample_Wavelengths[i] + Range,
                                    Spacing[0])
                Results = []
                for j in To_Test:
                    Results.append(self.Find_Required_Step(j, Sample_Pixels[i], False))
                Sample_Wavelengths[i] = To_Test[np.argmin(np.abs(np.array(Results) - Steps))]
            Range = Spacing[0]
            Spacing = Spacing[1:]

        #Use estimates to find a quadratic relation

        Coefficents = np.polyfit(Sample_Pixels, Sample_Wavelengths, 2)

        #Optimise this relation over all pixels

        def Loss(Coefficents):
            Wavelengths = np.polyval(np.polyfit(Sample_Pixels, Sample_Wavelengths, 2), Pixel_Array)
            Diff = []
            for i in range(len(Pixel_Array)):
                Diff.append(self.Find_Required_Step(Wavelengths[i], Pixel_Array[i], False) - Steps)
            return np.sum(np.abs(Diff))

        Coefficents = spo.minimize(Loss, Coefficents).x

        Wavelengths = np.polyval(np.polyfit(Sample_Pixels, Sample_Wavelengths, 2), Pixel_Array)

        return Wavelengths

    def Find_Required_Step(self, Wavelength, Pixel, Require_Integer=True):
        """Return the motor step value that would place a wavelength on a given CCD pixel.

        Args:
            Wavelength: Target wavelength in nm.
            Pixel: CCD pixel index the wavelength should land on.
            Require_Integer: If True, round the result to an int.

        Returns:
            int or float: The required stepper-motor position.

        Raises:
            ValueError: If the current grating has no supplied calibration.
        """

        if self.Grating_Number >= len(self.Calibration_Arrays) or len(
                self.Calibration_Arrays[self.Grating_Number]) == 0:  #Check calibration exists
            raise ValueError('Current grating is not calibrated! No calibration supplied!')

        Spline_Data = self.Spline_Data[self.Grating_Number]

        Coefficent_Blocks = []
        for i in range(len(Spline_Data[1])):
            Coefficent_Blocks.append(
                np.array([Spline_Data[1][i], Spline_Data[2][i], Spline_Data[3][i]]))

        #-----Calculate the 3x3 calibration matrix to use-----------

        Region = 0
        while Region < len(Spline_Data[0]) and Spline_Data[0][Region] < Wavelength:
            Region += 1

        if Region <= 1:
            Coefficents = Coefficent_Blocks[0]
        elif Region >= len(Spline_Data) - 1:
            Coefficents = Coefficent_Blocks[-1]
        else:
            Frac = (Wavelength - Spline_Data[0][Region - 1]) / (Spline_Data[0][Region] -
                                                                Spline_Data[0][Region - 1])
            Coefficents = (1 - Frac) * Coefficent_Blocks[Region -
                                                         2] + Frac * Coefficent_Blocks[Region - 1]

        #Perform Conversion

        Coefficents = np.sum(Coefficents * np.array([Wavelength**2, Wavelength, 1.]), axis=1)

        Output = (-Coefficents[1] - np.sqrt((Coefficents[1]**2) -
                                            (4 * Coefficents[0] *
                                             (Coefficents[2] - Pixel)))) / (2 * Coefficents[0])
        if Require_Integer is True:
            Output = int(Output)

        return Output

    def Move_Steps(self, Steps):
        """Move the grating by a number of stepper-motor steps and refresh the wavelength array.

        Args:
            Steps: Number of stepper-motor steps to move (may be negative).
        """

        if (
                Steps <= 0
        ):  # Taken from original code, assume there is an issue moving backwards that this corrects
            self.write("F0,%i\r" % (Steps - 1000))
            time.sleep(1)
            self.waitTillReady()
            self.write("F0,1000\r")
            self.waitTillReady()
        else:
            self.write("F0,%i\r" % Steps)
            time.sleep(1)
            self.waitTillReady()
        self.Wavelength_Array = self.Convert_Pixels_to_Wavelengths(
            np.array(list(range(self.Number_of_Pixels))))  #Update wavelength array

    def Set_Center_Wavelength(self, Wavelength):
        """Move the grating so ``Wavelength`` falls on the centre CCD pixel.

        Args:
            Wavelength: Desired centre wavelength in nm.

        Raises:
            ValueError: If ``ccd_size`` has not been set by a child class.
        """
        if self.ccd_size is None:
            raise ValueError('ccd_size must be set in child class')
        Centre_Pixel = int(self.ccd_size / 2)
        Required_Step = self.Find_Required_Step(Wavelength, Centre_Pixel)
        Current_Step = self.Motor_Steps()
        self.Move_Steps(Required_Step - Current_Step)

    def Get_Center_Wavelength(self):
        """Return the wavelength (nm) of the centre CCD pixel.

        Returns:
            float: The centre-pixel wavelength.
        """
        wls = self.Get_Wavelength_Array()
        return wls[len(wls) // 2]

    center_wavelength = property(Get_Center_Wavelength, Set_Center_Wavelength)

    def Slit(self, Width=None):
        """Query or set the entrance slit width in micrometres.

        A backlash correction is applied when widening the slit.

        Args:
            Width: ``None`` to query the current width, or the desired width in um to set.

        Returns:
            int or None: The current slit width when querying; ``None`` when setting.

        Note:
            When ``Width`` is ``None`` the function returns early, but when a positive ``Width`` is
            requested ``To_Move`` is only assigned inside the ``elif Width > 0`` branch, so a
            ``Width`` of ``0`` would raise ``UnboundLocalError`` at the following ``if To_Move``
            check. Logged rather than changed to avoid altering behaviour.
        """

        Current_Width = int(self.query("j0,0\r")[1:])

        if Width is None:
            return Current_Width
        elif Width > 0:
            To_Move = Width - Current_Width
        if To_Move == 0:
            return
        elif To_Move > 0:  # backlash correction
            self.write("k0,0,%i\r" % (To_Move + 100))
            self.waitTillReady()

            self.write("k0,0,-100\r")
            self.waitTillReady()
        else:
            self.write("k0,0,%i\r" % To_Move)
            self.waitTillReady()

    def _isBusy(self):
        """Return whether the Triax is currently unable to accept further commands.

        Returns:
            bool: ``True`` if busy, ``False`` if ready.
        """

        if self.query("E") == 'oz':
            return False
        else:
            return True

    def waitTillReady(self, Timeout=120):
        """Block until the Triax reports ready, polling once per second.

        Args:
            Timeout: Maximum time to wait in seconds before giving up.
        """

        Start_Time = time.time()

        while self._isBusy():
            time.sleep(1)
            if (time.time() - Start_Time) > Timeout:
                self._logger.warn('Timed out')
                print('Timed out')
                break

    def get_qt_ui(self):
        """Return a Qt widget for controlling this Triax.

        Returns:
            TriaxUI: The control widget bound to this instrument.
        """
        return TriaxUI(self)

    #-------------------------------------------------------------------------------------------------
    # The methods below are inherited from older code and are intentionally left untouched.

    def reset(self):
        """Reset the Triax and re-run the motor initialisation if the boot prompt is reached."""
        self.instr.write_raw(b'\xde')
        time.sleep(5)
        buff = self.query(" ")
        if buff == 'B':
            self.instr.write_raw(b'\x4f\x32\x30\x30\x30\x00')  # <O2000>0
            buff = self.query(" ")
        if buff == 'F':
            self._logger.debug("Triax is reset")
            self.setup()

    def setup(self):
        """Start the motor initialisation routine on the Triax."""
        self._logger.info("Initiating motor. This will take some time...")
        self.write("A")
        # time.sleep(60)
        # self.waitTillReady()
        # self.Grating(1)
        # self.Grating_Number = self.Grating()

    def exitLateral(self):
        """Route the beam through the lateral exit and entrance ports."""
        self.write("e0\r")
        self.write("c0\r")  # sets entrance mirror to lateral as well

    def exitAxial(self):
        """Route the beam through the axial exit and entrance ports."""
        self.write("f0\r")
        self.write("d0\r")  # sets the entrance mirror to axial as well


class TriaxUI(QtWidgets.QWidget, UiTools):
    """Qt control panel for a :class:`Triax`: centre wavelength, slit width and grating."""

    def __init__(self,
                 triax,
                 ui_file=os.path.join(os.path.dirname(__file__), 'triax_ui.ui'),
                 parent=None):
        """Build the UI and wire its widgets to ``triax``.

        Args:
            triax: The :class:`Triax` instrument this UI controls.
            ui_file: Path to the Qt Designer ``.ui`` layout file.
            parent: Optional parent Qt widget.
        """
        assert isinstance(triax, Triax), "instrument must be a Triax"
        super(TriaxUI, self).__init__()
        uic.loadUi(ui_file, self)
        self.triax = triax
        self.centre_wl_lineEdit.returnPressed.connect(self.set_wl_gui)
        self.slit_lineEdit.returnPressed.connect(self.set_slit_gui)
        self.centre_wl_lineEdit.setText(str(np.around(self.triax.center_wavelength)))
        self.slit_lineEdit.setText(str(self.triax.Slit()))
        eval('self.grating_' + str(self.triax.Grating()) + '_radioButton.setChecked(True)')
        for radio_button in range(3):
            eval('self.grating_' + str(radio_button) +
                 '_radioButton.clicked.connect(self.set_grating_gui)')

    def set_wl_gui(self):
        """Set the centre wavelength from the text in the wavelength field."""
        self.triax.Set_Center_Wavelength(float(self.centre_wl_lineEdit.text().strip()))

    def set_slit_gui(self):
        """Set the slit width from the text in the slit field."""
        self.triax.Slit(float(self.slit_lineEdit.text().strip()))

    def set_grating_gui(self):
        """Switch grating to match the radio button that triggered the signal.

        Raises:
            ValueError: If the sender is not one of the connected grating radio buttons.
        """
        s = self.sender()
        if s is self.grating_0_radioButton:
            self.triax.Grating(0)
        elif s is self.grating_1_radioButton:
            self.triax.Grating(1)
        elif s is self.grating_2_radioButton:
            self.triax.Grating(2)
        else:
            raise ValueError('radio buttons not connected!')
