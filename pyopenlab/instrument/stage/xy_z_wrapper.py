"""Combine a separate XY stage and Z stage into a single three-axis Stage."""
import numpy as np

from pyopenlab.instrument.stage import Stage


class XY_ZWrapper(Stage):
    """Present a 2-axis XY stage and a 1-axis Z stage as one x/y/z stage.

    Args:
        XY: Underlying stage providing the ``x`` and ``y`` axes.
        Z: Underlying stage providing the ``z`` axis.
        unit: Distance unit reported by the combined stage.
    """
    axis_names = ('x', 'y', 'z')

    def __init__(self, XY, Z, unit='u'):
        self.XY = XY
        self.Z = Z
        super().__init__(unit=unit)

    def get_position(self, axis=None):
        """Return the position of the combined stage.

        Args:
            axis: ``'x'``, ``'y'`` or ``'z'`` for a single axis, or ``None`` for
                all three.

        Returns:
            The XY position appended with the Z position when ``axis`` is
            ``None``, the single-axis position for a valid ``axis``, or ``None``
            if ``axis`` is not a recognised axis name.
        """
        if axis is None:
            return np.append(self.XY.position, self.Z.position)
        elif axis in self.axis_names:
            if axis in 'xy':
                return self.XY.get_position(axis=axis)
            elif axis == 'z':
                return self.Z.get_position()

    def move(self, x, axis=None, relative=False):
        """Move the combined stage, dispatching to the XY and Z sub-stages.

        Args:
            x: Target position(s). When ``axis`` is ``None``, a sequence whose
                first two elements drive XY and whose optional third element
                drives Z. Otherwise a scalar for the selected axis.
            axis: ``'x'``, ``'y'`` or ``'z'`` to move one axis, or ``None`` to
                move XY (and Z if a third coordinate is supplied).
            relative: If True, move relative to the current position.
        """
        if axis is None:
            self.XY.move(x[:2], relative=relative)
            if len(x) == 3:
                self.Z.move(x[2], relative=relative)

        elif axis in self.axis_names:
            if axis in 'xy':
                self.XY.move(x, axis=axis, relative=relative)
            elif axis == 'z':
                self.Z.move(x, relative=relative)
