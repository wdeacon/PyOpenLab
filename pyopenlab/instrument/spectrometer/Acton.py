# -*- coding: utf-8 -*-
"""VISA driver for the Princeton Instruments Acton SP-2750 monochromator.

The :class:`SP2750` class wraps the serial command set documented in the
manufacturer manual to control the centre wavelength, grating selection and
entrance/exit diverter mirrors, and to compute the per-pixel wavelength axis of
an attached detector from a JSON calibration file.

See ftp://ftp.princetoninstruments.com/public/manuals/Acton/SP-2750.pdf
"""
import json
import os
import re
import time

import numpy as np
from visa import VisaIOError

from pyopenlab.instrument.visa_instrument import VisaInstrument


class SP2750(VisaInstrument):
    """Acton SP-2750 monochromator controlled over a VISA serial connection."""

    @property
    def wavelength(self):
        """float: The present centre wavelength in nm (moves the grating when set)."""
        return self.get_wavelength()

    @wavelength.setter
    def wavelength(self, value):
        self.set_wavelength_fast(value)

    def __init__(self, address, calibration_file=None):
        """Open the monochromator and configure serial communications.

        Args:
            address: VISA resource address of the monochromator.
            calibration_file: Optional path to a JSON calibration file used by
                :meth:`get_wavelengths`. If None, a default file alongside this
                module is used on first access.
        """
        port_settings = dict(baud_rate=9600,
                             read_termination="\r\n",
                             write_termination="\r",
                             timeout=10000)
        super(SP2750, self).__init__(address, port_settings)
        self.clear_read_buffer()
        self._calibration_file = calibration_file

        self.metadata_property_names += ('wavelength',)

    def query(self, *args, **kwargs):
        """Send a command and validate the device's acknowledgement.

        The SP-2750 terminates a successful reply with "ok". This wrapper strips
        that status, and if it is missing performs additional reads until "ok"
        is seen.

        Args:
            *args: Positional arguments forwarded to the underlying VISA query.
            **kwargs: Keyword arguments forwarded to the underlying VISA query.

        Returns:
            The reply text with the "ok" status stripped, or the concatenated
            multi-read text if the status did not arrive on the first read.

        Raises:
            ValueError: If "ok" is not seen after more than ten extra reads.
        """
        full_reply = self.instr.query(*args, **kwargs)

        status = full_reply[-2:]
        reply = full_reply[:-2]

        if "?" in full_reply:
            self._logger.warn("Message  %s" % full_reply)

        if status == "ok":
            return reply.strip()
        else:
            self._logger.info("Multiple reads")
            read = str(full_reply)
            idx = 0
            while "ok" not in read:
                read += " | " + self.read()
                idx += 1
                if idx > 10:
                    raise ValueError("Too many multiple reads")
            return read

    def calibrate(self, wvl, to_device=True):
        """Apply a wavelength calibration correction (currently a no-op).

        Args:
            wvl: Wavelength in nm.
            to_device: True when converting a requested wavelength for the
                device, False when converting a value read back from it.

        Returns:
            The (currently uncorrected) wavelength.
        """
        if to_device:
            calibrated = wvl
        else:
            calibrated = wvl
        return calibrated

    # MOVEMENT COMMANDS
    def _wait(self):
        """Checks whether movement has finished"""
        time.sleep(1)
        t0 = time.time()
        while time.time() - t0 < 10 and not self.is_ready():
            try:
                if self.is_ready():
                    break
            except VisaIOError as e:
                time.sleep(1)  # This you get from testing

    def set_wavelength_fast(self, wvl):
        """Move to a destination wavelength at maximum motor speed.

        Args:
            wvl: Destination wavelength in nm. Accepts a float with up to 3
                decimal places, or a whole number with no decimal point.

        Returns:
            The device's reply once movement has finished.
        """

        self.write("%0.3f GOTO" % self.calibrate(wvl))
        # TODO: wait until the spectrometer replies OK
        self._wait()
        return self.read()

    def set_wavelength(self, wvl):
        """Move to a destination wavelength at the rate set by the last NM/MIN command.

        Args:
            wvl: Destination wavelength in nm. Accepts a float with up to 3
                decimal places, or a whole number with no decimal point.
        """

        self.write("%0.3f NM" % self.calibrate(wvl))

    def get_wavelength(self):
        """Read the present wavelength.

        Returns:
            The present wavelength in nm (0.01 nm resolution), calibration applied.
        """
        string = self.query("?NM")
        wvl = float(re.findall("([0-9]+\.[0-9]+) ", string)[0])
        return self.calibrate(wvl, False)

    def set_speed(self, rate):
        """Set the grating scan rate.

        Args:
            rate: Scan rate in nm/min (0.01 nm/min resolution).
        """
        self.query("%0.3f NM/MIN" % rate)

    def is_ready(self):
        """Return True if the monochromator has finished its current move."""
        return bool(self.query("MONO-?DONE"))

    # GRATING CONTROL
    def set_grating(self, index):
        """Select the grating to place into position.

        Up to nine gratings across three turrets are supported. The correct
        turret must already be selected via the TURRET command; this only chooses
        among the gratings on the installed turret.

        Args:
            index: Grating number from 1 to 9.
        """

        self.query("%d GRATING" % index)

    def get_grating(self):
        """Return the number (1-9) of the grating presently in use."""
        return self.query("?GRATING")

    def get_gratings(self):
        """Return the list of installed gratings with groove density and blaze.

        Returns:
            The device's grating listing; the present grating is marked with an
            arrow character.
        """
        return self.query("?GRATINGS")

    # DIVERTER MIRRORS
    @property
    def exit_mirror(self):
        """str: Exit diverter mirror position ('SIDE' or 'FRONT')."""
        self.query('EXIT-MIRROR')
        return self.query('?MIRROR')

    @exit_mirror.setter
    def exit_mirror(self, value):
        assert value in ['SIDE', 'FRONT']
        self.query('EXIT-MIRROR')
        self.query(value)

    @property
    def entrance_mirror(self):
        """str: Entrance diverter mirror position ('SIDE' or 'FRONT')."""
        self.query('ENT-MIRROR')
        return self.query('?MIRROR')

    @entrance_mirror.setter
    def entrance_mirror(self, value):
        assert value in ['SIDE', 'FRONT']
        self.query('ENT-MIRROR')
        self.query(value)

    # CALIBRATED MEASUREMENT
    @property
    def calibration_file(self):
        """Path to the calibration file"""
        if self._calibration_file is None:
            self._calibration_file = os.path.join(os.path.dirname(__file__),
                                                  'default_calibration.json')
        return self._calibration_file

    @calibration_file.setter
    def calibration_file(self, path):
        """Resolve a relative path against this module's directory as a .json file.

        Args:
            path: Path to the calibration file; relative paths are made absolute
                relative to this module's directory and given a ``.json`` suffix.

        Note:
            The extension check compares against ``'json'`` rather than ``'.json'``
            (``os.path.splitext`` returns the dot), so an already-``.json`` path is
            still treated as needing conversion. Left unfixed per the
            surgical-changes policy as it alters behaviour.
        """
        if not os.path.isabs(path):
            default_directory = os.path.dirname(__file__)
            path, ext = os.path.splitext(path)
            if ext != 'json':
                if ext != '':
                    self._logger.warn('Changing file type to JSON')
                ext = 'json'
                path = os.path.join(default_directory, path + '.' + ext)
        self._calibration_file = path

    def get_wavelengths(self):
        """Compute the per-pixel wavelength axis for a detector attached to the SP2750.

        Reads the detector size and dispersion (and optional offset) from the
        JSON calibration file, evaluates them as polynomials of the central
        wavelength, and spreads them across the detector pixels. Example JSONs::

            {"detector_size": 100, "dispersion": 0.01}
            {"detector_size": 100, "dispersion": [0.0001, 0.02]}
            {"detector_size": 2048,
             "dispersion": {"1": 0.014, "2": [0.0001, 0.02]},
             "offset": {"1": [0.00001, 1]}}

        Returns:
            A numpy array of wavelengths in nm, one per detector pixel.

        Note:
            Uses ``np.float``, which was removed in NumPy 1.24+; on a modern
            NumPy this raises ``AttributeError``. Left unfixed per the
            surgical-changes policy.
        """
        central_wavelength = self.wavelength

        with open(self.calibration_file, 'r') as dfile:
            calibration = json.load(dfile)
        detector_size = calibration['detector_size']

        dispersion = calibration['dispersion']
        if isinstance(dispersion, dict):
            current_grating = self.get_grating()
            dispersion = dispersion[current_grating]
        poly = np.poly1d(
            dispersion)  # poly1d handles it whether you give it a number on an iterable
        dispersion_value = poly(central_wavelength)

        offset_value = 0
        if 'offset' in calibration:
            offset = calibration['offset']
            if isinstance(offset, dict):
                current_grating = self.get_grating()
                offset = offset[current_grating]

            poly = np.poly1d(offset)
            offset_value = poly(central_wavelength)

        pixels = np.arange(detector_size, dtype=np.float)
        pixels -= np.mean(pixels)
        delta_wvl = pixels * dispersion_value
        return central_wavelength + delta_wvl + offset_value
