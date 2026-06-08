# -*- coding: utf-8 -*-
"""
Auto-aligning spectrometer: centres in on a nanoparticle after a short scan
"""

import threading
import time

from matplotlib.figure import Figure
#from pyopenlab.utils.traitsui_mpl_qt import MPLFigureEditor
import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize

from pyopenlab.instrument import Instrument
import pyopenlab.instrument.spectrometer
import pyopenlab.instrument.stage
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs

#from scipy.odr import odrpack as odr


class SpectrometerAligner(Instrument):
    """Drive a stage to maximise spectrometer signal on a nanoparticle.

    Couples a spectrometer to a 3-axis stage and offers several search strategies
    (circle, grid, focus sweep) that move the stage and refine its position by
    optimising a merit function built from the measured spectrum.
    """

    def __init__(self, spectrometer, stage):
        """Store the instruments and initialise alignment state.

        Args:
            spectrometer: Spectrometer exposing ``read_spectrum``, ``background``,
                ``metadata`` and ``integration_time``.
            stage: 3-axis stage exposing ``position`` and ``move``.
        """
        super(SpectrometerAligner, self).__init__()
        self.spectrometer = spectrometer
        self.stage = stage
        self.align_to_raw_spectra = False
        self.settling_time = 0.3
        self.spectrum_mask = None
        self._action_lock = threading.RLock()

    def merit_function(self):
        """Return the scalar figure of merit to be maximised.

        Reads a spectrum, optionally subtracts the background and restricts to
        the configured pixel mask, then sums the result.

        Returns:
            float: Sum (ignoring NaNs) of the (optionally background-subtracted,
            optionally masked) spectrum.
        """
        spectrum = self.spectrometer.read_spectrum()
        if not self.align_to_raw_spectra and self.spectrometer.background.shape == spectrum.shape:
            spectrum -= self.spectrometer.background
        if self.spectrum_mask is None:
            return np.nansum(spectrum)
        else:
            return np.nansum(spectrum[self.spectrum_mask])

    def _do_circle_iteration_fired(self):
        """Run :meth:`iterate_circle` in a background thread (GUI button hook)."""
        threading.Thread(target=self.iterate_circle,
                         kwargs=dict(radius=self.step_size, npoints=self.number_of_points)).start()

    def iterate_circle(self, radius, npoints=3, print_move=True, **kwargs):
        """Sample spectra around a circle and refine the position.

        Args:
            radius (float): Circle radius in stage units.
            npoints (int): Number of points sampled around the circle.
            print_move (bool): Whether to print the move applied.
            **kwargs: Forwarded to :meth:`iterate_on_points`.

        Returns:
            tuple: ``(positions, powers, mean_position)`` from
            :meth:`iterate_on_points`.
        """
        angles = [2 * np.pi / float(npoints) * float(i) for i in range(npoints)]
        points = [np.array([np.cos(a), np.sin(a), 0]) * radius for a in angles]
        return self.iterate_on_points(points, include_here=True, print_move=print_move, **kwargs)

    def iterate_grid(self, stepsize, **kwargs):
        """Sample a 9-point grid and move to the brightest point.

        Args:
            stepsize (float): Grid spacing in stage units.
            **kwargs: Forwarded to :meth:`iterate_on_points`.

        Returns:
            tuple: ``(positions, powers, mean_position)`` from
            :meth:`iterate_on_points`.
        """
        points = [
            np.array([i, j, 0]) * stepsize
            for i in [-1, 0, 1]
            for j in [-1, 0, 1]
            if not (i == 0 and j == 0)]
        return self.iterate_on_points(points, include_here=True, fit_method="maximum", **kwargs)

    def _do_focus_iteration_fired(self):
        """Run :meth:`iterate_z` in a background thread (GUI button hook)."""
        threading.Thread(target=self.iterate_z, args=[self.step_size]).start()

    def iterate_z(self, dz, print_move=True):
        """Sample spectra above and below the current focus and refine z.

        Args:
            dz (float): Focus step in stage units.
            print_move (bool): Whether to print the move applied.

        Returns:
            tuple: ``(positions, powers, mean_position)`` from
            :meth:`iterate_on_points`.
        """
        return self.iterate_on_points([np.array([0, 0, z]) for z in [-dz, dz]],
                                      print_move=print_move)

    def iterate_on_points(self,
                          points,
                          include_here=True,
                          print_move=True,
                          plot_args={},
                          fit_method="centroid"):
        """Visit a set of points and refine the stage position toward the peak.

        The merit function is evaluated at each point (in stage units, relative
        to the current position), then the stage is moved to the position implied
        by the chosen fit method. The minimum reading is subtracted to avoid
        negative values and speed up convergence.

        Args:
            points (list[numpy.ndarray]): Offsets from the current position to
                visit.
            include_here (bool): If True, also use the present position as a
                sample; helps stability when ``points`` form e.g. a circle.
            print_move (bool): Whether to print the move applied.
            plot_args (dict): Extra keyword args forwarded to
                :meth:`plot_alignment`.
            fit_method (str): One of ``"centroid"``, ``"parabola"``,
                ``"gaussian"`` or ``"maximum"`` selecting how the target position
                is derived from the samples. Parabola and gaussian fall back to
                centroid on failure.

        Returns:
            tuple: ``(positions, powers, mean_position)`` where ``positions`` and
            ``powers`` are the sampled stage positions and merit values and
            ``mean_position`` is the position moved to.
        """
        #NB we're not bothering with sample coordinates here...
        self._action_lock.acquire()
        here = np.array(self.stage.position)
        positions = [here]
        powers = [self.merit_function()]
        for p in points:  #iterate through the points and measure the merit function
            self.stage.move(here + p)
            time.sleep(self.settling_time)
            positions.append(self.stage.position)
            powers.append(self.merit_function())
        if fit_method == "parabola":  #parabolic fit: fit a 2D parabola to the data.  More responsive but less stable than centre of mass.
            try:
                pos = np.array(positions) - np.mean(positions, axis=0)
                powers = np.array(powers)
                mean_position = np.mean(
                    pos, axis=0
                )  #default to no motion, (as the polyfit will fail if there's no motion in one axis) ??should this be positions (measured) or points (specified)?
                axes_with_motion = np.where(
                    np.std(np.array(points), axis=0) > 0
                )[0]  #don't try to fit axes where there's no motion (nb the [0] is necessary because the return value from np.where is a tuple)
                #model: power = a +b.x + c.<crossterms>
                N = len(axes_with_motion)  #number of axes
                quadratic = np.ones((powers.shape[0], 2 * N + 1))
                for i, a in enumerate(axes_with_motion):
                    quadratic[:, i + 1] = pos[:, a]  #put linear terms in the matrix
                for i, a in enumerate(axes_with_motion):
                    quadratic[:, i + 1 +
                              N] = pos[:,
                                       a]  #put quadratic terms in the matrix (ignore cross terms for now...)
                p = np.linalg.lstsq(quadratic,
                                    powers)[0]  #use least squares to fast-fit a 2D parabola
                print("quadratic fit: ", p)
                for i, a in enumerate(axes_with_motion):
                    if p[i + 1 + N] > 0:
                        mean_position[a] = np.Inf * p[
                            i +
                            1]  #if the parabola is happy/flat, assume we are moving the maximum step
                        print("warning: there is no maximum on axis %d" % a)
                    else:
                        mean_position[a] = -p[i + 1] / (
                            2 * p[i + N + 1]
                        )  #if there's a maximum in the fitted curve, assume that's where we should be
                        print("axis %d has a maximum at %.2f" % (a, mean_position[a]))
                for i in range(mean_position.shape[0]):
                    if mean_position[i] > np.max(pos[:, i]) / 2:
                        mean_position[i] = np.max(
                            pos[:, i]) / 2  #constrain to lie within the positions supplied
                    if mean_position[i] < np.min(pos[:, i]) / 2:
                        mean_position[i] = np.min(pos[:, i]) / 2  #so we don't move too far
                mean_position += np.mean(positions, axis=0)
            except:
                print("Quadratic fit failed, falling back to centroid.")
                fit_method = "centroid"
        if fit_method == "gaussian":
            try:
                pos = np.array(positions)
                powers = np.array(powers)
                mean_position = np.mean(
                    pos, axis=0
                )  #default to no motion, (as the polyfit will fail if there's no motion in one axis) ??should this be positions (measured) or points (specified)?
                axes_with_motion = np.where(
                    np.std(np.array(points), axis=0) > 0
                )[0]  #don't try to fit axes where there's no motion (nb the [0] is necessary because the return value from np.where is a tuple)
                N = len(axes_with_motion)

                def error_from_gaussian(p):
                    gaussian = p[0] + p[1] * np.exp(-np.sum(
                        (pos - p[2:2 + N])**2 / (2 * p[2 + N:2 + 2 * N]**2), axis=1))
                    return np.mean((powers - gaussian)**2)

                ret = scipy.optimize.minimize(error_from_gaussian, [0, np.max(powers)] +
                                              list(mean_position) + list(np.ones(N) * 0.3))
                print(ret)
                assert ret.success
                for i, a in enumerate(axes_with_motion):
                    mean_position[a] = ret.x[i + 2]
            except:
                print("Gaussian fit failed, falling back to centroid.")
                fit_method = "centroid"
        if fit_method == "centroid":
            powers = np.array(
                powers) - np.min(powers) * 1.1 + np.max(powers) * 0.1  #make sure no powers are <0
            mean_position = np.dot(powers, positions) / np.sum(powers)
        if fit_method == "maximum":  #go to the brightest point
            powers = np.array(powers)
            mean_position = np.array(positions)[powers.argmax(), :]

        if print_move:
            print("moving %.3f, %.3f, %.3f" % tuple(mean_position - here))
        try:
            self.stage.move(mean_position)
        except:
            print("Positions:\n", positions)
            print("Powers: ", powers)
            print("Mean Position: ", mean_position)
        self._action_lock.release()
        self.plot_alignment(positions, powers, mean_position, **plot_args)
        return positions, powers, mean_position

    def optimise(self, tolerance, max_steps=10, stepsize=0.5, npoints=3, dz=0.5, verbose=False):
        """Repeatedly move and take spectra to find the peak in x, y and z.

        Each iteration performs ``iterate_circle(stepsize, npoints)`` then
        ``iterate_z(dz)``. The loop stops when the distance moved falls below
        ``tolerance``.

        Args:
            tolerance (float or numpy.ndarray): Convergence threshold. A scalar
                applies uniformly; a 3-element array applies per-axis tolerances
                to x, y, z, with convergence when
                ``sum(dx**2 / tolerance**2) <= 1.0``.
            max_steps (int): Maximum number of iterations.
            stepsize (float): Circle radius passed to :meth:`iterate_circle`.
            npoints (int): Number of circle points per iteration.
            dz (float): Focus step passed to :meth:`iterate_z`.
            verbose (bool): If True, print per-move and iteration-count output.

        Returns:
            tuple: ``(positions, powers)`` recorded over the iterations.

        Warning:
            This is experimental and can be unstable; the focus has a tendency to
            wander.
        """
        self._action_lock.acquire()
        positions = [np.array(self.stage.position)]
        powers = [self.merit_function()]
        for i in range(max_steps):
            pos = self.iterate_circle(stepsize, npoints, print_move=verbose)[2]
            pos = self.iterate_z(dz, print_move=verbose)[2]
            positions.append(pos)
            powers.append(self.merit_function())
            if np.sum((positions[-1] - positions[-2])**2 / tolerance**2) <= 1.0:
                break
            else:
                time.sleep(self.settling_time)
        if verbose:
            print("performed %d iterations" % (len(positions) - 1))
        self._action_lock.release()
        self.plot_alignment(positions, powers, [np.NaN, np.NaN])
        return positions, powers

    def _do_XY_optimisation_fired(self):
        """Run :meth:`optimise_2D` in a background thread (GUI button hook)."""
        threading.Thread(target=self.optimise_2D,
                         args=[self.tolerance],
                         kwargs=dict(stepsize=self.step_size,
                                     npoints=self.number_of_points)).start()

    def optimise_2D(self,
                    tolerance=0.03,
                    max_steps=10,
                    stepsize=0.2,
                    npoints=3,
                    print_move=True,
                    reduce_integration_time=True):
        """Repeatedly grid-search in x and y to find the peak.

        Runs :meth:`iterate_grid` until the movement produced is smaller than
        ``tolerance``.

        Args:
            tolerance (float): Convergence threshold on the Euclidean step size.
            max_steps (int): Maximum number of iterations.
            stepsize (float): Grid spacing passed to :meth:`iterate_grid`.
            npoints (int): Accepted for API symmetry; not used by the grid search.
            print_move (bool): Whether to print each move.
            reduce_integration_time (bool): If True, temporarily divide the
                spectrometer integration time by 3 during the search and restore
                it afterwards.

        Returns:
            tuple: ``(positions, powers)`` recorded over the iterations.
        """
        if reduce_integration_time == True:
            start_expo = self.spectrometer.integration_time
            self.spectrometer.integration_time = start_expo / 3.0
        self._action_lock.acquire()
        positions = [np.array(self.stage.position)]
        powers = [self.merit_function()]
        for i in range(max_steps):
            #pos = self.iterate_circle(stepsize,npoints,print_move,plot_args={'color':"blue",'cla':(i==0)})[2]
            pos = self.iterate_grid(stepsize,
                                    print_move=print_move,
                                    plot_args={
                                        'color': "blue",
                                        'cla': (i == 0)})[2]
            positions.append(pos)
            powers.append(self.merit_function())
            if np.sqrt(np.sum((positions[-1] - positions[-2])**2)) < tolerance:
                break
        print("performed %d iterations" % (len(positions) - 1))
        self._action_lock.release()
        self.plot_alignment(positions,
                            powers, [np.NaN, np.NaN],
                            cla=False,
                            fade=False,
                            color="green")
        if reduce_integration_time == True:
            self.spectrometer.integration_time = start_expo
        return positions, powers

    def z_scan(self, dz=np.arange(-4, 4, 0.4)):
        """Take spectra at relative z positions and return them as a 2D array.

        Args:
            dz (numpy.ndarray): Relative z offsets (stage units) to visit.

        Returns:
            ArrayWithAttrs: Stacked spectra with the spectrometer metadata
            attached.
        """
        spectra = []
        here = self.stage.position
        self.spectrometer.read_spectrum()
        self.spectrometer.read_spectrum(
        )  #reads spectrum trice to clear cached junk before taking measurement
        for z in dz:
            self.stage.move(np.array([0, 0, z]) + here)
            time.sleep(self.settling_time)
            spectra.append(self.spectrometer.read_spectrum())
        self.stage.move(here)
        return ArrayWithAttrs(spectra, attrs=self.spectrometer.metadata)

    def plot_alignment(self, positions, powers, mean_position, cla=True, fade=True, **kwargs):
        """Plot an alignment run so its progress can be inspected.

        Args:
            positions: Sampled stage positions.
            powers: Merit values at each position.
            mean_position: Final position moved to.
            cla (bool): Whether to clear the axes before plotting.
            fade (bool): Whether to fade existing plots instead of clearing.
            **kwargs: Forwarded to the scatter plot.

        Note:
            The plotting body is commented out; this is currently a no-op.
        """
        pass


#        x = [p[0] for p in positions]
#        y = [p[1] for p in positions]
#        powers = np.array(powers)
#        s = powers/powers.max() * 200
#        ax = self.figure.axes[0]
#        if cla:
#            ax.cla()
#        elif fade: #fade out existing plots
#            for c in ax.collections:
#                c.set_color(tuple(np.array(c.get_facecolor())*0.5+np.array([1,1,1,1])*0.5))
#        ax.scatter(x,y,s=s,**kwargs)
#        ax.plot([mean_position[0]],[mean_position[1]], 'r+')
#        canvas = self.figure.canvas
#        if canvas is not None:
#            canvas.draw()


def fit_parabola(positions, powers, *args):
    """Fit a 2D parabola to power-versus-position data and return the step.

    Args:
        positions: Stage positions sampled.
        powers: Merit values at each position.
        *args: Ignored; accepted for call-site compatibility.

    Returns:
        numpy.ndarray: Offset from the mean position to the fitted peak,
        constrained to lie within the sampled positions.
    """
    positions = np.array(positions)
    powers = np.array(powers)
    mean_position = np.mean(
        positions, axis=0
    )  #default to no motion, (as the polyfit will fail if there's no motion in one axis) ??should this be positions (measured) or points (specified)?
    axes_with_motion = np.where(
        np.std(positions, axis=0) > 0
    )[0]  #don't try to fit axes where there's no motion (nb the [0] is necessary because the return value from np.where is a tuple)
    #model: power = a +b.x + c.<crossterms>
    N = len(axes_with_motion)  #number of axes
    quadratic = np.ones((powers.shape[0], 2 * N + 1))
    for i, a in enumerate(axes_with_motion):
        quadratic[:, i + 1] = positions[:, a]  #put linear terms in the matrix
    for i, a in enumerate(axes_with_motion):
        quadratic[:, i + 1 +
                  N] = positions[:,
                                 a]  #put quadratic terms in the matrix (ignore cross terms for now...)
    p = np.linalg.lstsq(quadratic, powers)[0]  #use least squares to fast-fit a 2D parabola
    for i, a in enumerate(axes_with_motion):
        if p[i + 1 + N] > 0:
            mean_position[a] = np.Inf * p[
                i + 1]  #if the parabola is happy/flat, assume we are moving the maximum step
        else:
            mean_position[a] = -p[i + 1] / (
                2 * p[i + N + 1]
            )  #if there's a maximum in the fitted curve, assume that's where we should be
    for i in range(mean_position.shape[0]):
        if mean_position[i] > np.max(positions[:, i]):
            mean_position[i] = np.max(positions[:,
                                                i])  #constrain to lie within the positions supplied
        if mean_position[i] < np.min(positions[:, i]):
            mean_position[i] = np.min(positions[:, i])  #so we don't move too far
    return mean_position - np.mean(positions, axis=0)


def plot_alignment(positions, powers, mean_position):
    """Scatter-plot alignment samples with the chosen position marked.

    Args:
        positions: Sampled stage positions.
        powers: Merit values at each position, used to scale marker sizes.
        mean_position: Position to mark with a red cross.
    """
    x = [p[0] for p in positions]
    y = [p[1] for p in positions]
    powers = np.array(powers)
    s = powers / powers.max() * 20
    plt.scatter(x, y, s=s)
    plt.plot([mean_position[0]], [mean_position[1]], 'r+')
    plt.show(block=False)


if __name__ == "__main__":
    import pyopenlab.instrument.spectrometer.seabreeze as seabreeze
    seabreeze.shutdown_seabreeze()  #just in case...
    import pyopenlab.instrument.stage.prior as prior_stage
    stage = prior_stage.ProScan("COM3")
    spectrometer = seabreeze.OceanOpticsSpectrometer(0)
    aligner = SpectrometerAligner(spectrometer, stage)
    spectrometer.edit_traits()
    aligner.edit_traits()
