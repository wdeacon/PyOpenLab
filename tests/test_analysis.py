"""Tests for pyopenlab.analysis Spectrum / RamanSpectrum and helpers."""
import h5py
import numpy as np
import pytest

from pyopenlab.analysis import RamanSpectrum
from pyopenlab.analysis import remove_cosmic_ray
from pyopenlab.analysis import Spectrum


def test_spectrum_construction_and_wl_alias():
    wl = np.linspace(500, 600, 10)
    s = Spectrum(np.arange(10), wl)
    assert isinstance(s, np.ndarray)
    np.testing.assert_array_equal(s.wavelengths, wl)
    np.testing.assert_array_equal(s.wl, wl)


def test_spectrum_length_mismatch_raises():
    with pytest.raises(AssertionError):
        Spectrum(np.arange(10), np.arange(9))


def test_spectrum_split_selects_range():
    wl = np.arange(10.0)
    s = Spectrum(np.arange(10.0), wl)
    chunk = s.split(2, 5)
    # lower inclusive, upper exclusive
    np.testing.assert_array_equal(chunk.wavelengths, [2, 3, 4])
    np.testing.assert_array_equal(np.asarray(chunk), [2, 3, 4])


def test_spectrum_norm_peaks_at_one():
    s = Spectrum(np.array([1.0, 2.0, 4.0]), np.arange(3))
    n = s.norm()
    assert np.isclose(np.asarray(n).max(), 1.0)
    np.testing.assert_allclose(np.asarray(n), [0.25, 0.5, 1.0])


def test_spectrum_squash_sums_time_series():
    wl = np.arange(4.0)
    s = Spectrum(np.array([[1.0, 1.0, 1.0, 1.0], [2.0, 2.0, 2.0, 2.0]]), wl)
    squashed = s.squash()
    assert squashed.shape == (4,)
    np.testing.assert_array_equal(np.asarray(squashed), [3, 3, 3, 3])


def test_spectrum_from_h5_applies_background_and_reference(tmp_path):
    wl = np.linspace(500, 600, 5)
    raw = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    path = tmp_path / 'spec.h5'
    with h5py.File(path, 'w') as f:
        dset = f.create_dataset('spectrum', data=raw)
        dset.attrs['wavelengths'] = wl
        dset.attrs['background'] = 5.0
        dset.attrs['reference'] = 105.0
    with h5py.File(path, 'r') as f:
        s = Spectrum.from_h5(f['spectrum'])
    expected = (raw - 5.0) / (105.0 - 5.0)
    np.testing.assert_allclose(np.asarray(s), expected)
    np.testing.assert_array_equal(s.wavelengths, wl)


def test_raman_shifts_computed_from_wavelengths():
    wl = np.linspace(633.0, 750.0, 50)
    laser = 632.8
    r = RamanSpectrum(np.ones(50), wavelengths=wl, laser_wavelength=laser)
    expected = (1.0 / (laser * 1e-9) - 1.0 / (wl * 1e-9)) / 100.0
    np.testing.assert_allclose(r.shifts, expected)
    # x axis of a RamanSpectrum is the shift axis.
    np.testing.assert_allclose(r.x, expected)


def test_raman_laser_wavelength_is_per_instance():
    # Regression for the Phase-1 change: laser_wavelength is a constructor
    # parameter (default 632.8), not a shared class variable.
    wl = np.linspace(633.0, 750.0, 20)
    r_hene = RamanSpectrum(np.ones(20), wavelengths=wl, laser_wavelength=632.8)
    r_785 = RamanSpectrum(np.ones(20), wavelengths=wl, laser_wavelength=785.0)
    assert r_hene.laser_wavelength == 632.8
    assert r_785.laser_wavelength == 785.0
    # Different excitation -> different shift axes; the two must not interfere.
    assert not np.allclose(r_hene.shifts, r_785.shifts)


def test_raman_default_laser_wavelength():
    r = RamanSpectrum(np.ones(5), wavelengths=np.linspace(633, 640, 5))
    assert r.laser_wavelength == 632.8


def test_raman_shifts_supplied_directly_bypass_computation():
    shifts = np.array([0.0, 100.0, 200.0, 300.0])
    r = RamanSpectrum(np.ones(4), shifts=shifts)
    np.testing.assert_array_equal(r.shifts, shifts)


def test_raman_requires_shifts_or_wavelengths():
    with pytest.raises(AssertionError):
        RamanSpectrum(np.ones(4))


def test_remove_cosmic_ray_suppresses_spike():
    spectrum = np.full(500, 100.0)
    spectrum[250] = 10000.0
    cleaned = remove_cosmic_ray(spectrum)
    # The spike must be pulled far down toward the baseline...
    assert cleaned[250] < 1000.0
    # ...without disturbing the rest of the (flat) spectrum.
    assert np.allclose(cleaned[:100], 100.0)
    # Input is not modified in place.
    assert spectrum[250] == 10000.0
