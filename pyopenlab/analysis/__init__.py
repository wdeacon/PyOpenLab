"""Spectral data classes and analysis utilities for pyopenlab."""
from functools import cached_property
from pathlib import Path
import re

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.signal import savgol_filter

H5_TEMPLATE = r'\S*(\d{4})-(\d{2})-(\d{2})\S*.h5'
# allow somestuff1_2021-01-05_someotherstuff.h5


def load_h5(location='.'):
    """Return the most recent dated HDF5 file in a directory.

    Args:
        location: Path to the directory to search (default: current directory).

    Returns:
        h5py.File: The latest HDF5 file opened in read-only mode.

    Raises:
        ValueError: If no HDF5 file matching the expected date pattern is found.
    """
    path = Path(location)
    candidates_dates = [(f, [int(m) for m in match.groups()]) for f in path.iterdir()\
                        if (match := re.match(H5_TEMPLATE, f.name))]
    if candidates_dates:
        return h5py.File(path / max(candidates_dates, key=lambda cd: cd[1])[0], 'r')
    else:
        raise ValueError('No suitable h5 file found')


def latest_scan(file):
    """Return the last ``ParticleScannerScan`` group in an HDF5 file.

    Args:
        file: An open h5py File object.

    Returns:
        h5py.Group: The ``ParticleScannerScan`` group with the highest index.
    """
    return file[max(file,
                    key=lambda x: int(x.split('_')[-1])
                    if x.startswith('ParticleScannerScan') else -1)]


class Spectrum(np.ndarray):
    """A numpy ndarray with a ``wavelengths`` attribute and spectral helper methods.

    Can be 1-D (single spectrum) or 2-D (time series or z-scan), with the
    wavelength axis always on the last dimension.
    """

    def __new__(cls, spectrum, wavelengths, *args, **kwargs):
        """Create a Spectrum from array data and a wavelengths array.

        Args:
            spectrum: Array-like spectral data. The last dimension must match
                the length of ``wavelengths``.
            wavelengths: 1-D array of wavelength values in nm.
            *args: Extra positional arguments forwarded to ``np.asarray``.
            **kwargs: Extra keyword arguments forwarded to ``np.asarray``.

        Returns:
            Spectrum: The new spectrum with ``.wavelengths`` set.
        """
        assert len(wavelengths) == np.shape(spectrum)[-1]

        obj = np.asarray(spectrum).view(cls)
        obj.wavelengths = np.asarray(wavelengths)
        return obj

    def __array_finalize__(self, obj):
        """Propagate ``.wavelengths`` when NumPy creates a derived array."""
        if obj is None:
            return
        if not obj.shape:
            return np.array(obj)
        self.wavelengths = getattr(obj, 'wavelengths', np.arange(obj.shape[-1]))

    def __reduce__(self):
        # Get the parent's __reduce__ tuple
        pickled_state = super().__reduce__()
        # Create our own tuple to pass to __setstate__
        new_state = pickled_state[2] + (self.wavelengths,)
        # Return a tuple that replaces the parent's __setstate__ tuple with our own
        return (pickled_state[0], pickled_state[1], new_state)

    def __setstate__(self, state):
        self.wavelengths = state[-1]  # Set the info attribute
        # Call the parent's __setstate__ with the other tuple elements.
        super().__setstate__(state[0:-1])

    @classmethod
    def from_h5(cls, dataset):
        """Create a Spectrum from an HDF5 dataset, applying background and reference.

        If ``background`` and ``reference`` attributes are present on the dataset
        they are used to normalise: ``(data - bg) / (ref - bg)``.

        Args:
            dataset: An h5py Dataset with a ``wavelengths`` attribute and
                optionally ``background`` and ``reference`` attributes.

        Returns:
            Spectrum: The loaded and normalised spectrum.
        """
        attrs = dataset.attrs
        ref = attrs.get('reference', 1)
        bg = attrs.get('background', 0)
        return cls((dataset[()] - bg) / (ref - bg), dataset.attrs['wavelengths'])

    @property
    def wl(self):
        """Wavelengths array (shorthand for ``self.wavelengths``)."""
        return self.wavelengths

    @wl.setter
    def wl(self, value):
        self.wavelengths = np.array(value)

    @property
    def x(self):
        """The x axis used by :meth:`split` and related methods (wavelengths by default)."""
        return self.wavelengths  # wavelengths unless subclassed

    def split(self, lower=-np.inf, upper=np.inf):
        """Return the portion of the spectrum between ``lower`` and ``upper``.

        Args:
            lower: Lower bound on the x axis (inclusive). Defaults to ``-inf``.
            upper: Upper bound on the x axis (exclusive). Defaults to ``+inf``.

        Returns:
            Spectrum: Sliced spectrum with matching wavelengths.
        """
        if upper < lower:
            upper, lower = lower, upper
        condition = (lower <= self.x) & (self.x < upper)
        # '<=' allows recombination of an array into the original
        return self.__class__(self.T[condition].T, self.x[condition])

    def norm(self):
        """Return the spectrum normalised by its maximum value.

        Returns:
            Spectrum: Spectrum divided by its peak intensity.
        """
        return self.__class__(self / self.ravel().max(), self.x)

    def squash(self):
        """Condense a 2-D time series into a single summed spectrum.

        Returns:
            Spectrum: 1-D spectrum summed along axis 0.
        """
        return self.__class__(self.sum(axis=0), self.x)

    def smooth(self, sigma):
        """Smooth the spectrum with a Gaussian filter.

        Args:
            sigma: Standard deviation of the Gaussian kernel in pixels.

        Returns:
            Spectrum: Smoothed spectrum.
        """
        return self.__class__(gaussian_filter(self, sigma), self.x)

    def savgol_smooth(self, *args, **kwargs):
        """Smooth the spectrum with a Savitzky-Golay filter.

        Args:
            *args: Forwarded to ``scipy.signal.savgol_filter``.
            **kwargs: Forwarded to ``scipy.signal.savgol_filter``.

        Returns:
            Spectrum: Smoothed spectrum.
        """
        return self.__class__(savgol_filter(self, *args, **kwargs), self.x)

    def remove_cosmic_ray(self, thresh=5, smooth=30, max_iterations=10):
        """Remove cosmic ray spikes from the spectrum.

        Args:
            thresh: Number of noise standard deviations above which a point
                is considered a spike (default 5).
            smooth: Gaussian sigma used to estimate the underlying spectrum
                (default 30).
            max_iterations: Maximum cleaning passes (default 10).

        Returns:
            Spectrum: Cleaned spectrum with spikes replaced by smoothed values.
        """
        func = lambda s: remove_cosmic_ray(
            s, thresh=thresh, smooth=smooth, max_iterations=max_iterations)
        if len(self.shape) == 2:
            return self.__class__(
                [func(s) for s in self],
                self.x,
            )
        return self.__class__(func(self), self.x)


class RamanSpectrum(Spectrum):
    """A :class:`Spectrum` whose x axis is Raman shift in cm⁻¹.

    Shifts are computed from ``wavelengths`` and ``laser_wavelength`` on first
    access, or can be supplied directly via the ``shifts`` argument.

    Pass the excitation wavelength at construction time:

    >>> spec = RamanSpectrum(data, wavelengths=wls, laser_wavelength=785.)

    For multiple excitation wavelengths in the same analysis, subclass or
    simply pass the appropriate ``laser_wavelength`` to each constructor call.
    """

    def __new__(cls,
                spectrum,
                shifts=None,
                wavelengths=None,
                laser_wavelength=632.8,
                *args,
                **kwargs):
        """Create a RamanSpectrum from array data and either shifts or wavelengths.

        Args:
            spectrum: Array-like spectral data.
            shifts: 1-D array of Raman shift values in cm⁻¹. If supplied,
                ``wavelengths`` is not required and shifts are used directly.
            wavelengths: 1-D array of wavelength values in nm. Shifts are
                computed lazily from ``wavelengths`` and ``laser_wavelength``
                on first access.
            laser_wavelength: Excitation laser wavelength in nm. Defaults to
                632.8 (HeNe). Only used when shifts are computed from
                wavelengths; ignored if ``shifts`` is provided directly.
            *args: Extra positional arguments (unused, for subclass compatibility).
            **kwargs: Extra keyword arguments (unused, for subclass compatibility).

        Returns:
            RamanSpectrum: The new spectrum with ``.wavelengths``,
            ``._shifts``, and ``.laser_wavelength`` set as appropriate.

        Raises:
            AssertionError: If both ``shifts`` and ``wavelengths`` are None.
        """
        assert not (shifts is None and wavelengths is None),\
        'must supply shifts or wavelengths'
        obj = np.asarray(spectrum).view(cls)
        if wavelengths is not None:
            wavelengths = np.asarray(wavelengths)
        obj.wavelengths = wavelengths
        if shifts is not None:
            shifts = np.asarray(shifts)
        obj._shifts = shifts
        obj.laser_wavelength = laser_wavelength
        return obj

    def __array_finalize__(self, obj):
        """Propagate ``.wavelengths``, ``._shifts``, and ``.laser_wavelength`` when NumPy creates a derived array."""
        if obj is None:
            return
        if not obj.shape:
            return np.array(obj)
        self.wavelengths = getattr(obj, 'wavelengths', np.arange(obj.shape[-1]))
        self._shifts = getattr(obj, '_shifts', None)
        self.laser_wavelength = getattr(obj, 'laser_wavelength', 632.8)

    def __reduce__(self):
        # Get the parent's __reduce__ tuple
        pickled_state = super().__reduce__()
        # Create our own tuple to pass to __setstate__
        new_state = pickled_state[2] + (self.wavelengths,)
        # Return a tuple that replaces the parent's __setstate__ tuple with our own
        return (pickled_state[0], pickled_state[1], new_state)

    def __setstate__(self, state):
        self.wavelengths = state[-1]  # Set the info attribute
        # Call the parent's __setstate__ with the other tuple elements.
        super().__setstate__(state[0:-1])

    @classmethod
    def from_h5(cls, dataset, laser_wavelength=632.8):
        """Create a RamanSpectrum from an HDF5 dataset, applying background and reference.

        If ``background`` and ``reference`` attributes are present on the dataset
        they are used to normalise: ``(data - bg) / (ref - bg)``.

        Args:
            dataset: An h5py Dataset with a ``wavelengths`` attribute and
                optionally ``background`` and ``reference`` attributes.
            laser_wavelength: Excitation laser wavelength in nm. Defaults to
                632.8 (HeNe).

        Returns:
            RamanSpectrum: The loaded and normalised spectrum, with shifts
            computed lazily from wavelengths on first access.
        """
        attrs = dataset.attrs
        ref = attrs.get('reference', 1)
        bg = attrs.get('background', 0)
        return cls((dataset[()] - bg) / (ref - bg),
                   wavelengths=dataset.attrs['wavelengths'],
                   laser_wavelength=laser_wavelength)

    @cached_property  # only ever calculated once per instance
    def shifts(self):
        """Raman shift axis in cm⁻¹, computed from wavelengths or returned directly if supplied."""
        if self._shifts is None:
            return (1. / (self.laser_wavelength * 1e-9) - 1. / (self.wl * 1e-9)) / 100.
        return self._shifts

    @property
    def x(self):
        """The x axis used by :meth:`split` and related methods (Raman shifts in cm⁻¹)."""
        return self.shifts


def remove_cosmic_ray(spectrum, thresh=5, smooth=30, max_iterations=10):
    """Remove cosmic ray spikes from a 1-D spectrum.

    Iteratively identifies and replaces sharp spikes by comparing each point
    against a Gaussian-smoothed version of the spectrum. Mainly tested on
    dark-field spectra; the spikiness of Raman spectra makes simple spike
    removal unreliable there.

    Args:
        spectrum: 1-D array-like of spectral intensity values.
        thresh: Number of noise standard deviations above which a point is
            considered a cosmic ray spike. Lower values catch smaller spikes
            but risk clipping genuine signal peaks. Defaults to 5.
        smooth: Gaussian sigma (in pixels) used to estimate the underlying
            spectrum. Should be large enough to preserve the spectral shape
            while eliminating the spike. Defaults to 30.
        max_iterations: Maximum cleaning passes. Most spectra converge in
            1–3 iterations. Defaults to 10.

    Returns:
        numpy.ndarray: Cleaned spectrum with spike regions replaced by the
        smoothed estimate.
    """
    _len = len(spectrum)
    cleaned = np.copy(spectrum)  # prevent modification in place

    for i in range(max_iterations):
        noise_spectrum = cleaned / gaussian_filter(cleaned, smooth)
        # ^ should be a flat, noisy line, with a large spike where there's
        # a cosmic ray.
        noise_level = np.sqrt(np.var(noise_spectrum))
        # average deviation of a datapoint from the mean
        mean_noise = noise_spectrum.mean()  # should be == 1
        spikes = np.arange(_len)[noise_spectrum > mean_noise + (thresh * noise_level)]
        # the indices of the datapoints that are above the threshold

        # now we add all data points to either side of the spike that are
        # above the noise level (but not necessarily the thresh*noise_level)
        rays = set()
        for spike in spikes:
            for side in (-1, 1):  # left and right
                step = 0
                while 0 <= (coord := spike + (side * step)) <= _len - 1:
                    # staying in the spectrum

                    if noise_spectrum[coord] > mean_noise + noise_level:
                        rays.add(coord)
                        step += 1
                    else:
                        break
        rays = list(rays)  # convert to list for indexing
        if rays:  # if there are any cosmic rays
            cleaned[rays] = gaussian_filter(cleaned, smooth)[rays]
            # replace the regions with the smooothed spectrum
            continue  # and repeat, as the smoothed spectrum will still be
            # quite affected by the cosmic ray.

        # until no cosmic rays are found
        return cleaned
    return cleaned


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    wls = np.linspace(633, 750, 1600)
    spec = np.random.randint(300, 600, size=1600)

    rspec = RamanSpectrum(spec, wavelengths=wls)

    RamanSpectrum.laser_wavelength = 700
    plt.figure()
    plt.plot(rspec.shifts, rspec, label='shifts')
    rspec2 = RamanSpectrum(spec, wavelengths=wls)
    plt.plot(rspec2.shifts, rspec2, label='center of 700')
    plt.legend()
