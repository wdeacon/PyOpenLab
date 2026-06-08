# -*- coding: utf-8 -*-
"""Phase pattern generators and iterative Fourier transform hologram algorithms for the SLM.

Each pattern generator takes an input phase array and returns the input plus an added phase term,
so generators can be chained. The iterative Fourier transform routines (``mraf``,
``gerchberg_saxton``) compute holograms that reproduce a target intensity.

Note:
    ``mraf`` and ``test_ifft_smoothness`` use ``np.float`` / ``np.bool``, which were removed in
    NumPy 1.24; they will raise ``AttributeError`` on recent NumPy. Replace with the builtin
    ``float`` / ``bool`` to restore them.
"""

from __future__ import division

from builtins import range
from builtins import zip

from matplotlib import gridspec
import matplotlib.pyplot as plt
import numpy as np
# import pyfftw
from scipy import misc

# TODO: performance quantifiers for IFT algorithms (smoothness, efficiency)
# TODO: compare initial phase methods in IFT algorithms: quadratic phase; starting in the real plane with a flat phase
# TODO: compare CPU and GPU


def _get_coordinate_arrays(image, center=None):
    """Create x and y coordinate arrays in pixel units, centred on a given point.

    Args:
        image (numpy.ndarray): 2D array whose shape sets the coordinate grid size.
        center (tuple, optional): Centre of the grid. If each value is ``< 1`` it is treated as a
            relative centre (with the SLM edges at ``[-1, 1]``); otherwise it is in pixel units. If
            None, the geometric centre is used.

    Returns:
        tuple: Two 2D :class:`numpy.ndarray` coordinate grids ``(x, y)``.
    """
    shape = np.shape(image)
    if center is None:
        center = [int(s // 2) for s in shape]
    elif any(np.array(center) < 1):
        center = [int(s // 2 + c * s) for s, c in zip(shape, center)]
    yx = [np.arange(shape[idx]) - center[idx] for idx in range(2)[::-1]]
    x, y = np.meshgrid(*yx)
    return x, y


def constant(input_phase, offset):
    """Add a uniform phase offset.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        offset (float): Constant phase offset in radians.

    Returns:
        numpy.ndarray: ``input_phase + offset``.
    """
    return input_phase + offset


def calibration_responsiveness(input_phase, grey_level, axis=0):
    """Generate a half-and-half pattern for calibrating phase retardation versus addressing voltage.

    Image the reflected beam directly onto a camera to create fringes; the fringe shift as a
    function of voltage gives the responsiveness. Assumes the retardation is uniform across the SLM.
    If it is not, see https://doi.org/10.1364/AO.43.006400 for how to measure it.

    Args:
        input_phase (numpy.ndarray): Phase pattern (used only for its shape).
        grey_level (float): Phase level applied to one half of the panel.
        axis (int): Axis along which to split the panel: 0 (rows) or 1 (columns).

    Returns:
        numpy.ndarray: Phase pattern that is zero on one half and ``grey_level`` on the other.

    Raises:
        ValueError: If ``axis`` is not 0 or 1.
    """
    shape = np.shape(input_phase)
    centers = [int(x // 2) for x in shape]
    out_phase = np.zeros(shape)
    if axis == 0:
        out_phase[centers[0]:] = grey_level
    elif axis == 1:
        out_phase[:, centers[1]:] = grey_level
    else:
        raise ValueError('Unrecognised axis: %d' % axis)
    return out_phase


def gratings(input_phase, grating_const_x=0, grating_const_y=0):
    """Add a linear phase ramp corresponding to a grating or steering mirror.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        grating_const_x (float): Period (in pixels) of the grating along x. Default 0 means none.
        grating_const_y (float): Period (in pixels) of the grating along y. Default 0 means none.

    Returns:
        numpy.ndarray: ``input_phase`` plus the grating phase.
    """
    x, y = _get_coordinate_arrays(input_phase)
    phase = np.zeros(x.shape)
    if np.abs(grating_const_x) > 1:
        phase += (2 * np.pi / grating_const_x) * x
    if np.abs(grating_const_y) > 1:
        phase += (2 * np.pi / grating_const_y) * y

    return input_phase + phase


def multispot_grating(input_phase, grating_const, n_spot, center=None):
    """Add a phase that divides the SLM into angular segments, each with its own grating direction.

    This produces multiple focal spots arranged in a ring.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        grating_const (float): Inverse period (in pixels) of the gratings.
        n_spot (int): Number of angular segments (spots) to divide the SLM into.
        center (tuple, optional): Centre passed to :func:`_get_coordinate_arrays`.

    Returns:
        numpy.ndarray: ``input_phase`` plus the multi-spot grating phase.
    """
    x, y = _get_coordinate_arrays(input_phase, center)
    theta = np.arctan2(y, x) + np.pi

    phase = np.zeros(x.shape)
    if n_spot > 1:
        for i in range(n_spot):
            gx = np.pi * grating_const * np.cos((i + 0.5) * 2 * np.pi / n_spot)
            gy = np.pi * grating_const * np.sin((i + 0.5) * 2 * np.pi / n_spot)
            mask = np.zeros(x.shape)
            mask[theta <= (i + 1) * 2 * np.pi / n_spot] = 1
            mask[theta <= i * 2 * np.pi / n_spot] = 0
            phase += (x * gx + y * gy) * mask
    return input_phase + phase


def focus(input_phase, curvature=0, center=None):
    """Add a quadratic phase pattern corresponding to a perfect lens.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        curvature (float): Inverse focal length of the lens, in arbitrary units.
        center (tuple, optional): Centre passed to :func:`_get_coordinate_arrays`.

    Returns:
        numpy.ndarray: ``input_phase`` plus the lens phase.
    """
    x, y = _get_coordinate_arrays(input_phase, center)
    phase = curvature * (x**2 + y**2)
    return input_phase + phase


def astigmatism(input_phase, amplitude=0, angle=0, center=None):
    """Add a cylindrical phase pattern corresponding to astigmatism.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        amplitude (float): Cylindrical curvature.
        angle (float): Angle (in degrees) between the cylindrical curvature and the input axes.
        center (tuple, optional): Centre passed to :func:`_get_coordinate_arrays`.

    Returns:
        numpy.ndarray: ``input_phase`` plus the astigmatism phase.
    """
    x, y = _get_coordinate_arrays(input_phase, center)
    rho = np.sqrt(x**2 + y**2)
    phi = np.arctan2(x, y)

    horizontal = amplitude * np.cos(angle * np.pi / 180)
    diagonal = amplitude * np.sin(angle * np.pi / 180)

    phase = (horizontal * np.cos(2 * phi) + diagonal * np.sin(2 * phi)) * rho**2

    return input_phase + phase


def vortexbeam(input_phase, order, angle, center=None):
    """Add a helical phase pattern corresponding to an optical vortex.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        order (int): Vortex order (topological charge).
        angle (float): Orientation of the vortex, in degrees.
        center (tuple, optional): Centre of the vortex, passed to :func:`_get_coordinate_arrays`.

    Returns:
        numpy.ndarray: ``input_phase`` plus the vortex phase.
    """
    # shape = np.shape(input_phase)
    # if center is None:
    #     center = [int(old_div(x, 2)) for x in shape]
    # elif any(np.array(center) < 1):
    #     center = [int(old_div(x, 2) + y*x) for x, y in zip(shape, center)]
    #
    # x = np.arange(shape[1]) - center[1]
    # y = np.arange(shape[0]) - center[0]
    # x, y = np.meshgrid(x, y)
    x, y = _get_coordinate_arrays(input_phase, center)

    phase = order * (np.angle(x + y * 1j) + angle * np.pi / 180.)

    return input_phase + phase


def linear_lut(input_phase, contrast, offset):
    """Wrap the phase to ``[0, 2*pi)`` and apply a linear contrast and offset mapping.

    Args:
        input_phase (numpy.ndarray): Phase pattern to remap.
        contrast (float): Multiplicative scaling applied to the wrapped phase.
        offset (float): Additive offset, applied as ``offset * pi``.

    Returns:
        numpy.ndarray: The remapped phase.
    """
    out_phase = np.copy(input_phase)
    # out_phase -= out_phase.min()
    out_phase %= 2 * np.pi - 0.000001
    out_phase *= contrast
    out_phase += offset * np.pi
    return out_phase


"""Iterative Fourier Transform algorithms"""


def direct_superposition(input_phase, k_vectors, phases=None):
    """Add a hologram phase that diffracts light into a set of spots given by k-vectors.

    Builds a field by directly superposing plane waves, then takes the phase of its Fourier
    transform.

    Args:
        input_phase (numpy.ndarray): Phase pattern to add to.
        k_vectors (sequence): Sequence of ``(kx, ky)`` spatial frequencies, one per target spot.
        phases (sequence, optional): Phase of each plane wave. Defaults to random phases.

    Returns:
        numpy.ndarray: ``input_phase`` plus the superposition hologram phase.
    """
    if phases is None:
        phases = np.random.random(len(k_vectors))
    shape = np.shape(input_phase)
    x = np.arange(shape[1]) - int(shape[1] // 2)
    y = np.arange(shape[0]) - int(shape[0] // 2)
    x, y = np.meshgrid(x, y)

    real_plane = np.zeros(shape)
    for k_vec, phase in zip(k_vectors, phases):
        real_plane += np.exp(1j * 2 * np.pi * (k_vec[0] * x + k_vec[1] * y + phase))

    return input_phase + np.angle(np.fft.fftshift(np.fft.fft2(real_plane)))


def mraf(original_phase,
         target_intensity,
         input_field=None,
         mixing_ratio=0.4,
         signal_region_size=0.5,
         iterations=30):
    """Run the Mixed-Region Amplitude Freedom algorithm for continuous patterns.

    See https://doi.org/10.1364/OE.16.002176.

    Args:
        original_phase (numpy.ndarray or float): Base phase the result is added to.
        target_intensity (numpy.ndarray): Desired output intensity distribution.
        input_field (numpy.ndarray, optional): Initial SLM-plane field. Defaults to a field that
            focuses uniform illumination onto the signal region.
        mixing_ratio (float): Fraction of amplitude freedom given to the signal region.
        signal_region_size (float): Relative radius of the signal region.
        iterations (int): Number of iterations to run.

    Returns:
        numpy.ndarray: ``original_phase`` plus the computed input-plane phase.

    Note:
        Uses ``np.float`` (removed in NumPy 1.24+); raises ``AttributeError`` on recent NumPy.
    """
    shp = target_intensity.shape
    x, y = np.ogrid[-shp[1] // 2:shp[1] // 2, -shp[0] // 2:shp[0] // 2]
    x, y = np.meshgrid(x, y)

    target_intensity = np.asarray(target_intensity, np.float)
    if input_field is None:
        # By default, the initial phase focuses a uniform SLM illumination onto the signal region
        input_phase = ((x**2 / (shp[1] / (signal_region_size * 2 * np.sqrt(2)))) +
                       (y**2 / (shp[0] / (signal_region_size * 2 * np.sqrt(2)))))
        input_field = np.exp(1j * input_phase)
    # Normalising the input field and target intensity to 1 (doesn't have to be 1, but they have to be equal)
    input_field /= np.sqrt(np.sum(np.abs(input_field)**2))
    target_intensity /= np.sum(target_intensity)

    # This can leave the center of the SLM one or two pixels
    mask = (x**2 + y**2) < (signal_region_size * np.min(shp))**2
    signal_region = np.ones(shp) * mixing_ratio
    signal_region[~mask] = 0
    noise_region = np.ones(shp) * (1 - mixing_ratio)
    noise_region[mask] = 0
    input_intensity = np.abs(input_field)**2

    for _ in range(iterations):
        output_field = np.fft.fft2(input_field)
        # makes sure power out = power in, so that the distribution of power in signal and noise
        # regions makes sense
        output_field = output_field / np.sqrt(np.prod(shp))
        output_field = np.fft.fftshift(output_field)
        output_phase = np.angle(output_field)

        mixed_field = signal_region * np.sqrt(target_intensity) * np.exp(
            1j * output_phase) + noise_region * output_field
        mixed_field = np.fft.ifftshift(mixed_field)

        input_field = np.fft.ifft2(mixed_field)
        input_phase = np.angle(input_field)
        input_field = np.sqrt(input_intensity) * np.exp(1j * input_phase)
        # print(np.sum(np.abs(input_field)**2), np.sum(target_intensity), np.sum(np.abs(output_field)**2))
    return original_phase + input_phase


def gerchberg_saxton(original_phase, target_intensity, input_field=None, iterations=30):
    """Run the Gerchberg-Saxton algorithm for continuous patterns.

    Simplest version: FFT factors, intensity normalisation and FFT shifts are not tracked since
    they are all discarded anyway.

    Args:
        original_phase (numpy.ndarray or float): Base phase the result is added to.
        target_intensity (numpy.ndarray): Desired output intensity distribution.
        input_field (numpy.ndarray, optional): Initial SLM-plane field. Defaults to uniform.
        iterations (int): Number of iterations to run; must be positive.

    Returns:
        numpy.ndarray: ``original_phase`` plus the computed input-plane phase.

    Raises:
        AssertionError: If ``iterations <= 0``.
    """
    assert iterations > 0
    shp = target_intensity.shape
    target_intensity = np.fft.fftshift(
        target_intensity)  # this matrix is only used in the Fourier plane
    if input_field is None:
        input_field = np.ones(shp) * np.exp(1j * np.zeros(shp))
    input_intensity = np.abs(input_field)**2
    for _ in range(iterations):
        output_field = np.fft.fft2(
            input_field)  # don't have to normalise since the intensities are replaced
        output_phase = np.angle(output_field)
        output_field = np.sqrt(target_intensity) * np.exp(1j * output_phase)

        input_field = np.fft.ifft2(output_field)
        input_phase = np.angle(input_field)
        input_field = np.sqrt(input_intensity) * np.exp(1j * input_phase)
    return original_phase + input_phase


def test_ifft_smoothness(alg_func, *args, **kwargs):
    """Evaluate the smoothness of calculated vs target pattern per iteration of an IFFT algorithm.

    Smoothness is the sum of the absolute difference over the area of interest. For most algorithms
    the area of interest is the whole plane; for MRAF it is only the signal region.

    Args:
        alg_func (callable): The IFFT algorithm to test (:func:`gerchberg_saxton` or :func:`mraf`).
        *args: Positional arguments forwarded to ``alg_func``.
        **kwargs: Keyword arguments forwarded to ``alg_func`` (e.g. ``iterations``).

    Returns:
        numpy.ndarray: Smoothness value at each iteration.

    Raises:
        ValueError: If ``alg_func`` is not a recognised algorithm.

    Note:
        Uses ``np.bool`` (removed in NumPy 1.24+); raises ``AttributeError`` on recent NumPy when
        ``alg_func`` is :func:`gerchberg_saxton`.
    """
    target = np.asarray(misc.face()[:, :, 0], np.float)
    x, y = _get_coordinate_arrays(target)
    shp = target.shape
    # x, y = np.ogrid[old_div(-shp[1], 2):old_div(shp[1], 2), old_div(-shp[0], 2):old_div(shp[0], 2)]
    # x, y = np.meshgrid(x, y)
    mask = (x**2 + y**2) > (0.2 * np.min(shp))**2
    target[mask] = 0
    target /= np.sum(target)

    iterations = 60
    if 'iterations' in kwargs:
        iterations = kwargs['iterations']
    # The algorithms only return the final phase, so to evaluate the smoothness at each iteration, need to set the
    # algorithm to only run one step at a time
    kwargs['iterations'] = 1

    # Defining a mask and a mixing_ratio for calculating the smoothness later
    if alg_func == gerchberg_saxton:
        mask = np.ones(shp, dtype=np.bool)
        mixing_ratio = 1
    elif alg_func == mraf:
        x, y = np.ogrid[-shp[1] // 2:shp[1] // 2, -shp[0] // 2:shp[0] // 2]
        x, y = np.meshgrid(x, y)
        signal_region_size = 0.5
        if 'signal_region_size' in kwargs:
            signal_region_size = kwargs['signal_region_size']
        mask = (x**2 + y**2) < (signal_region_size * np.min(shp))**2
        mixing_ratio = 0.4
        if 'mixing_ratio' in kwargs:
            mixing_ratio = kwargs['mixing_ratio']
    else:
        raise ValueError('Unrecognised algorithm')

    smth = []
    outputs = []
    for indx in range(iterations):
        init_phase = alg_func(0, target, *args, **kwargs)
        input_field = np.exp(1j * init_phase)
        kwargs['input_field'] = input_field
        output = np.fft.fftshift(np.fft.fft2(np.exp(1j * init_phase))) / (np.prod(shp))
        output_int = np.abs(output)**2
        # print(np.sum(np.abs(output_int)), np.sum(np.abs(output_int)[mask]))
        smth += [np.sum(np.abs(output_int - mixing_ratio * target)[mask]) / np.sum(mask)]
        outputs += [output]

    fig = plt.figure(figsize=(8 * shp[1] / shp[0] * 2, 8))
    gs = gridspec.GridSpec(1, 2)
    gs2 = gridspec.GridSpecFromSubplotSpec(5, 6, gs[0], 0.001, 0.001)
    reindex = np.linspace(0, iterations - 1, 30)
    ax = None
    for indx, _gs in zip(reindex, gs2):
        indx = int(indx)
        ax = plt.subplot(_gs, sharex=ax, sharey=ax)
        ax.imshow(np.abs(outputs[indx]))
        ax.text(shp[1] / 2., 0, '%d=%.3g' % (indx, smth[indx]), ha='center', va='top', color='w')
        ax.set_xticklabels([])
        ax.set_yticklabels([])
    ax2 = plt.subplot(gs[1])
    ax2.semilogy(smth)
    return np.array(smth)


def test_ifft_basic(alg_func, *args, **kwargs):
    """Test whether an IFFT algorithm's final phase reproduces an initial target.

    Creates an image target (the centre of the ``scipy.misc.face()`` image), runs ``alg_func`` on
    it, and plots the results for comparison by eye.

    Args:
        alg_func (callable): The IFFT algorithm to test (:func:`gerchberg_saxton` or :func:`mraf`).
        *args: Positional arguments forwarded to ``alg_func``.
        **kwargs: Keyword arguments forwarded to ``alg_func`` (e.g. ``mixing_ratio``).

    Returns:
        tuple: ``(output, target)`` where ``output`` is the reconstructed complex field and
        ``target`` is the normalised target intensity.

    Note:
        Uses ``np.float`` (removed in NumPy 1.24+); raises ``AttributeError`` on recent NumPy.
    """
    if 'mixing_ratio' in kwargs:
        intensity_correction = kwargs['mixing_ratio']
    else:
        intensity_correction = 1
    target = np.asarray(misc.face()[:, :, 0], np.float)
    x, y = _get_coordinate_arrays(target)
    shp = target.shape
    # x, y = np.ogrid[old_div(-shp[1], 2):old_div(shp[1], 2), old_div(-shp[0], 2):old_div(shp[0], 2)]
    # x, y = np.meshgrid(x, y)
    mask_size = 0.2
    mask = (x**2 + y**2) > (mask_size * np.min(shp))**2
    target[mask] = 0
    target /= np.sum(target)  # the target intensity is normalised to 1

    init_phase = np.zeros(target.shape)
    # Making an input field that focuses light on the target pattern reduces vortex creation and improves pattern
    input_field = np.ones(shp) * np.exp(1j * 2 * mask_size * np.min(shp) * ((x / np.max(x))**2 +
                                                                            (y / np.max(y))**2))
    kwargs['input_field'] = input_field
    phase = alg_func(init_phase, target, *args, **kwargs)
    output = np.fft.fftshift(np.fft.fft2(np.exp(1j * phase))) / (np.prod(shp))
    print(np.sum(np.abs(output)**2), np.sum(np.abs(output[~mask])**2),
          np.sum(np.abs(output[mask])**2))
    _errors = (target - np.abs(output)**2) / target
    errors = _errors[np.abs(_errors) != np.inf]
    avg = np.sqrt(np.mean(errors**2))

    fig, axs = plt.subplots(2, 2, sharey=True, sharex=True, gridspec_kw=dict(wspace=0.01))
    vmin, vmax = (np.min(target), np.max(target))
    axs[0, 0].imshow(target, vmin=vmin, vmax=vmax)
    axs[0, 0].set_title('Target')
    axs[1, 0].imshow(phase)
    axs[1, 0].set_title('Input Phase')
    vmin *= intensity_correction
    vmax *= intensity_correction
    axs[0, 1].imshow(np.abs(output)**2, vmin=vmin, vmax=vmax)
    axs[0, 1].set_title('Output')
    axs[1, 1].imshow(np.angle(output))
    axs[1, 1].set_title('Output Phase')
    fig.suptitle(r'$\sqrt{\sum\left(\frac{target-output}{target}\right)^2}=$%g' % avg)
    plt.show()

    return output, target


if __name__ == "__main__":
    test_ifft_basic(gerchberg_saxton)
