# -*- coding: utf-8 -*-
"""Combined Andor camera and Kymera spectrograph instrument.

Pairs an :class:`~pyopenlab.instrument.camera.Andor.Andor` detector with a
:class:`~pyopenlab.instrument.spectrometer.Kymera.Kymera` spectrograph so the
detector's x axis can be calibrated in wavelength (or Raman shift) units.
"""
import numpy as np

from pyopenlab.instrument.camera.Andor import Andor
from pyopenlab.instrument.spectrometer.Kymera import Kymera


class Kandor(Andor):
    """Wrapper coupling a Kymera spectrograph to an Andor detector."""

    def __init__(self,
                 pixel_number=1600,
                 pixel_width=16,
                 use_shifts=False,
                 laser_wl=632.8,
                 white_shutter=None):
        """Create the combined instrument and configure the spectrograph.

        Args:
            pixel_number (int): Number of detector pixels along the dispersion
                axis, pushed to the Kymera for calibration.
            pixel_width (float): Detector pixel width in microns, pushed to the
                Kymera for calibration.
            use_shifts (bool): If True, ``get_x_axis`` returns Raman shifts (in
                wavenumbers) relative to ``laser_wl`` instead of wavelengths.
            laser_wl (float): Excitation laser wavelength in nm, used to convert
                wavelengths to Raman shifts.
            white_shutter: Optional shutter object stored for callers that close
                the white-light source during a capture.
        """

        super().__init__()
        self.kymera = Kymera()
        self.kymera.pixel_number = pixel_number
        self.kymera.pixel_width = pixel_width
        self.use_shifts = use_shifts
        self.laser_wl = laser_wl
        self.white_shutter = white_shutter
        self.metadata_property_names += ('slit_width', 'wavelengths')
        self.ImageFlip = 0

    def get_x_axis(self, use_shifts=None):
        """Return the detector x axis from the Kymera calibration.

        Falls back to a plain pixel-index range when the calibration reads all
        zeros (an uncalibrated spectrograph).

        Args:
            use_shifts (bool, optional): Override of the instance ``use_shifts``
                setting; see Note.

        Returns:
            numpy.ndarray or range or list: Raman shifts in wavenumbers when
            shifts are requested, otherwise the wavelength calibration (nm), or a
            ``range`` of pixel indices if uncalibrated.

        Note:
            The shift branch is taken when ``use_shifts`` is None or False, which
            is the inverse of :meth:`Shamdor.get_x_axis`; calling
            ``get_x_axis(use_shifts=True)`` on a shifts-enabled instrument returns
            wavelengths rather than shifts. This is logged as a behavioural quirk
            and left unchanged to preserve existing behaviour.
        """
        X = self.kymera.GetCalibration()
        if all([not x for x in X]):  # if the list is all 0s
            X = range(len(X))
        if self.use_shifts and use_shifts in [None, False]:

            wavelengths = np.array(X)
            return (1. / (self.laser_wl * 1e-9) - 1. / (wavelengths * 1e-9)) / 100

        return X

    x_axis = property(get_x_axis)

    @property
    def slit_width(self):
        """float: Input slit width (microns) read from the Kymera."""
        return self.kymera.slit_width

    @property
    def wavelengths(self):
        """numpy.ndarray or range or list: Wavelength axis (nm).

        Requests the axis via ``get_x_axis(use_shifts=False)``. Note that because
        of the inverted shift branch documented in :meth:`get_x_axis`, a
        shifts-enabled instance still returns Raman shifts here.
        """
        return self.get_x_axis(use_shifts=False)


if __name__ == '__main__':
    k = Kandor()
    k.show_gui(block=False)
    ky = k.kymera
    ky.show_gui(block=False)
    k.MultiTrack = (2, 3, 50)
