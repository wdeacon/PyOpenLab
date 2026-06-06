"""Wrap a Thorlabs APT XY stage and a Piezoconcept Z stage as one xyz Stage."""
import numpy as np

from pyopenlab.instrument.stage import Stage
from pyopenlab.instrument.stage.apt_vcp_motor import DC_APT
from pyopenlab.instrument.stage.Piezoconcept_micro import Piezoconcept


class fake_stage(Stage):
    """No-op stand-in stage used when a real Z axis is not present."""

    def move(self, a, axis=1, relative=False):
        """Print the requested target instead of moving any hardware.

        Args:
            a: Requested position; printed and otherwise ignored.
            axis: Accepted for interface compatibility; ignored.
            relative: Accepted for interface compatibility; ignored.
        """
        print(a)

    def get_position(self):
        """Return ``0`` as a placeholder position."""
        return 0


class piezoconcept_thorlabsMSL02_wrapper(Stage):
    """Combine a Thorlabs APT XY motor and a Piezoconcept Z stage as one stage.

    Args:
        no_z: If True, use a :class:`fake_stage` for Z instead of a real
            Piezoconcept stage.

    Note:
        ``__init__`` does not call ``Stage.__init__`` (i.e. ``Instrument``
        initialisation is skipped); it only sets ``self.xy``, ``self.unit`` and
        ``self.z``. Logged, not fixed.
    """
    axis_names = ('x', 'y', 'z')

    def __init__(self, no_z=False):
        self.xy = DC_APT.get_instance()
        self.unit = 'u'
        if no_z:
            self.z = fake_stage()
        else:
            self.z = Piezoconcept.get_instance()

    def get_position(self):
        """Return the XY position with the Z position appended.

        Returns:
            The XY stage position appended with the Z stage position.
        """
        return np.append(self.xy.position, self.z.position)

    def move(self, x, axis=None, relative=False, block=True):
        """Move the combined stage, dispatching to the XY and Z sub-stages.

        Args:
            x: Target position(s). When ``axis`` is ``None``, a sequence of
                length 3 drives Z then XY, while a length-2 sequence drives XY
                only. Otherwise a scalar for the selected axis.
            axis: ``'x'``, ``'y'`` or ``'z'`` to move one axis, or ``None`` for
                a coordinated move from ``x``.
            relative: If True, move relative to the current position.
            block: Forwarded to the XY stage's ``move``; if True, that move
                blocks until complete.
        """
        print('move command', x, axis, relative)
        if axis == None:
            if len(x) == 3:
                self.z.move(x[2], relative=relative)
                try:
                    self.xy.move(x[:2], relative=relative, block=block)
                except Exception as e:
                    print(e)
                    self.xy.move(x[:2], relative=relative, block=block)
            elif len(x) == 2:
                try:
                    self.xy.move(x, relative=relative, block=block)
                except Exception as e:
                    print(e)
                    self.xy.move(x[:2], relative=relative, block=block)
        if axis in self.axis_names:
            if axis == 'x' or axis == 'y':
                self.xy.move(x, axis=axis, relative=relative)
            if axis == 'z':
                self.z.move(x, relative=relative)
