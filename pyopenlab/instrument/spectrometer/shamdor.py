# -*- coding: utf-8 -*-
"""Combined Andor camera and Shamrock spectrograph instrument.

Pairs an :class:`~pyopenlab.instrument.camera.Andor.Andor` detector with a
:class:`~pyopenlab.instrument.spectrometer.shamrock.Shamrock` spectrograph so the
detector's x axis can be calibrated in wavelength (or Raman shift) units.
"""

import numpy as np

from pyopenlab.instrument.camera.Andor import Andor
from pyopenlab.instrument.camera.Andor import AndorUI
from pyopenlab.instrument.shutter.BX51_uniblitz import Uniblitz
from pyopenlab.instrument.spectrometer.shamrock import Shamrock


class Shamdor(Andor):
    """Wrapper coupling a Shamrock spectrograph to an Andor detector."""

    def __init__(self,
                 pixel_number=1600,
                 pixel_width=16,
                 use_shifts=False,
                 laser_wl=632.8,
                 white_shutter=None):
        """Create the combined instrument and configure the spectrograph.

        Args:
            pixel_number (int): Number of detector pixels along the dispersion
                axis, pushed to the Shamrock for calibration.
            pixel_width (float): Detector pixel width in microns, pushed to the
                Shamrock for calibration.
            use_shifts (bool): If True, ``get_x_axis`` returns Raman shifts (in
                wavenumbers) relative to ``laser_wl`` instead of wavelengths.
            laser_wl (float): Excitation laser wavelength in nm, used to convert
                wavelengths to Raman shifts.
            white_shutter: Optional shutter object closed during a capture so the
                white-light source does not contaminate the spectrum.
        """
        self.shamrock = Shamrock()
        self.shamrock.pixel_number = pixel_number
        self.shamrock.pixel_width = pixel_width
        self.use_shifts = use_shifts
        self.laser_wl = laser_wl
        self.white_shutter = white_shutter
        super(Shamdor, self).__init__()
        self.metadata_property_names += ('slit_width', 'wavelengths')

    def get_x_axis(self, use_shifts=None):
        """Return the detector x axis from the Shamrock calibration.

        Args:
            use_shifts (bool, optional): Override the instance ``use_shifts``
                setting. Raman shifts are returned only when both the instance
                flag is set and this argument is None or True.

        Returns:
            numpy.ndarray or list: Raman shifts in wavenumbers when shifts are
            requested, otherwise the wavelength calibration (nm) in reversed
            pixel order.
        """
        if self.use_shifts and use_shifts in (None, True):

            wavelengths = np.array(self.shamrock.GetCalibration()[::-1])
            return (1. / (self.laser_wl * 1e-9) - 1. / (wavelengths * 1e-9)) / 100
        else:
            return self.shamrock.GetCalibration()[::-1]

    x_axis = property(get_x_axis)

    @property
    def slit_width(self):
        """float: Input slit width (microns) read from the Shamrock."""
        return self.shamrock.slit_width

    @property
    def wavelengths(self):
        """numpy.ndarray or list: Wavelength axis (nm), ignoring Raman shifts."""
        return self.get_x_axis(use_shifts=False)


def Capture(_AndorUI):
    """Acquire a raw frame, closing the white-light shutter if one is present.

    Bound onto :class:`~pyopenlab.instrument.camera.Andor.AndorUI` as its
    ``Capture`` method so the GUI capture button avoids white-light contamination.

    Args:
        _AndorUI: The AndorUI instance whose ``Andor`` owns the optional
            ``white_shutter``.
    """
    if _AndorUI.Andor.white_shutter is not None:
        isopen = _AndorUI.Andor.white_shutter.is_open()

        if isopen:
            _AndorUI.Andor.white_shutter.close_shutter()
        _AndorUI.Andor.raw_image(update_latest_frame=True)
        if isopen:
            _AndorUI.Andor.white_shutter.open_shutter()
    else:
        _AndorUI.Andor.raw_image(update_latest_frame=True)


setattr(AndorUI, 'Capture', Capture)

if __name__ == '__main__':
    # wutter = Uniblitz("COM10")
    # wutter.close_shutter()
    s = Shamdor()
    s.show_gui(blocking=False)
    s.shamrock.show_gui(block=False)
