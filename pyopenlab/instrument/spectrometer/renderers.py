"""Data renderers for spectrum datasets stored in HDF5 groups.

These renderers plug into the pyopenlab data-browser framework
(:mod:`pyopenlab.ui.data_renderers`) and know how to draw spectra held in an
HDF5 group as Matplotlib figures.
"""

from pyopenlab.ui.data_renderers import FigureRenderer


class SpectrumRenderer(FigureRenderer):
    """Render a single spectrum (wavelength vs. intensity) from an HDF5 group."""

    def __init__(self, h5group, parent=None):
        """Cache the wavelength and spectrum datasets from the group.

        Args:
            h5group: HDF5 group containing ``wavelength`` and ``spectrum`` datasets.
            parent: Optional parent Qt widget.
        """
        super(SpectrumRenderer, self).__init__(h5group, parent)
        self.wavelength = h5group['wavelength']
        self.spectrum = h5group['spectrum']

    def display_data(self):
        """Plot the spectrum against wavelength and redraw the figure canvas."""
        ax = self.fig.add_subplot(111)
        ax.plot(self.wavelength, self.spectrum)
        ax.set_xlabel('wavelength (nm)')
        self.fig.canvas.draw()

    @classmethod
    def is_suitable(cls, h5object):
        """Score how well this renderer matches the given HDF5 object.

        Args:
            h5object: Candidate HDF5 object to inspect.

        Returns:
            A suitability score (higher is better), or -1 if the object is not
            an HDF5 group.

        Note:
            The shape checks here are buggy: ``len(h5object['spectrum'].shape == 1)``
            evaluates ``shape == 1`` first (a bool) and then calls ``len`` on it,
            which raises ``TypeError``. As written the method never returns a
            positive score for a group containing a spectrum. Left unfixed per the
            surgical-changes policy; see the module owner before relying on it.
        """
        if not isinstance(h5object, h5py.Group):
            return -1
        if 'wavelength' in h5object and 'spectrum' in h5object:
            if len(h5object['spectrum'].shape == 1):
                return 3
            elif len(h5object['spectrum'].shape > 1):
                return 2


class MultiSpectrumRenderer(FigureRenderer):
    """Render two overlaid spectra (e.g. signal and reference) on twin axes."""

    def __init__(self, h5group, parent=None):
        """Cache both spectrum/wavelength dataset pairs from the group.

        Args:
            h5group: HDF5 group containing ``wavelength``/``spectrum`` and
                ``wavelength2``/``spectrum2`` datasets.
            parent: Optional parent Qt widget.
        """
        super(MultiSpectrumRenderer, self).__init__(h5group, parent)
        self.wavelength = h5group['wavelength']
        self.spectrum = h5group['spectrum']
        self.wavelength2 = h5group['wavelength2']
        self.spectrum2 = h5group['spectrum2']

    def display_data(self):
        """Plot both spectra on a shared x-axis with separate y-axes."""
        ax = self.fig.add_subplot(111)
        ax.plot(self.wavelength, self.spectrum)
        ax = ax.twinx()
        ax.plot(self.wavelength2, self.spectrum2)
        ax.set_xlabel('wavelength (nm)')
        self.fig.canvas.draw()

    @classmethod
    def is_suitable(cls, h5object):
        """Score how well this renderer matches the given HDF5 object.

        Args:
            h5object: Candidate HDF5 object to inspect.

        Returns:
            A suitability score (higher is better), or -1 if the object is not
            an HDF5 group.

        Note:
            As with :meth:`SpectrumRenderer.is_suitable`, the ``len(... == 1)``
            shape checks are buggy and raise ``TypeError`` rather than returning a
            score. Left unfixed per the surgical-changes policy.
        """
        if not isinstance(h5object, h5py.Group):
            return -1
        if 'wavelength2' in h5object and 'spectrum2' in h5object:
            if len(h5object['spectrum2'].shape == 1):
                return 5
            elif len(h5object['spectrum2'].shape > 1):
                return 4
        elif 'wavelength' in h5object and 'spectrum' in h5object:
            if len(h5object['spectrum'].shape == 1):
                return 3
            elif len(h5object['spectrum'].shape > 1):
                return 2
