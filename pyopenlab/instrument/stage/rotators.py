"""Qt helper to drive several rotators through angle lists and save payload data."""
from itertools import zip_longest
import random
import re
import winsound

import numpy as np

from pyopenlab.instrument import Instrument
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.thread_utils import background_action


def squawk():
    """Play five random beeps; the default payload for demonstrations.

    Returns:
        The string ``'I did a thing'``.
    """
    for i in range(5):
        winsound.Beep(random.randrange(37, 3500), random.randrange(70, 750))
    return 'I did a thing'


class Rotators(QtWidgets.QWidget, Instrument):
    """Qt GUI that steps several rotators through angle lists, saving payload data.

    Takes a mapping of label -> rotator (each must have a ``move`` method and a
    ``position``; typically a :class:`Stage` subclass) and builds a simple GUI.
    Each rotator gets a text field for a list of angles; on Run, the per-rotator
    angle lists are advanced together via :func:`itertools.zip_longest`, the
    ``payload`` is called at each step, and its return value is saved as a
    dataset. A rotator whose angles run out short stops moving while the others
    continue.

    Accepted text formats per field::

        A: 0, 10, 20
        B: 0, 45, 90
        C:                  # blank: rotator C never moves
        A: np.linspace(0, 360, 10)
        B: np.arange(0, 360, 10)
        C: 45               # single value: set once, then hold

    Args:
        rotators: Mapping of label to rotator object.
        payload: Callable invoked at each step; its return value is saved.

    Note:
        ``parse_edit`` runs ``eval`` on any field text beginning with ``np.``,
        so field contents are executed as Python. Logged, not fixed.
    """

    def __init__(self, rotators, payload=squawk):
        QtWidgets.QWidget.__init__(self)
        Instrument.__init__(self)
        self.rotators = rotators
        self.payload = payload

        self.edits = {r: [] for r in rotators}

        lines_widget = QtWidgets.QWidget()
        lines_layout = QtWidgets.QFormLayout()

        for label, r in rotators.items():
            l = QtWidgets.QLabel(label)
            self.edits[label] = (t := QtWidgets.QLineEdit())
            t.editingFinished.connect(self.textChanged)
            lines_layout.addRow(l, t)
        lines_widget.setLayout(lines_layout)
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(lines_widget)
        self.run_pushButton = QtWidgets.QPushButton('Run')
        self.run_pushButton.clicked.connect(self.run)
        layout.addWidget(self.run_pushButton)
        self.setLayout(layout)

    def textChanged(self):
        """Re-parse every rotator's text field into ``self.angles``."""
        self.angles = {r: self.parse_edit(self.edits[r]) for r in self.rotators}

    @staticmethod
    def parse_edit(edit):
        """Parse one field's text into a list of angles.

        Args:
            edit: The ``QLineEdit`` whose text is parsed.

        Returns:
            The evaluated list for ``np.`` expressions, a list of floats split
            on commas/spaces/semicolons otherwise, or an empty list if blank.
        """
        text = edit.text()
        if text:
            if text.startswith('np.'):
                return eval(text.strip()).tolist()
            split = (s for s in re.split(r',| |;', text) if s)
            return list(map(float, split))
        else:
            return []

    @background_action
    def run(self, checked):
        """Step every rotator through its angle list, saving payload data.

        Runs in a background thread. At each step, rotators with a remaining
        angle are moved, the payload is called, and its result is saved as a
        dataset annotated with every rotator's current position.

        Args:
            checked: Button-clicked state from the Run button; unused.
        """
        zipped_angles = zip_longest(*self.angles.values(), fillvalue=None)
        rotators = [self.rotators[key] for key in self.angles]
        for angles in (zipped_angles):
            for r, a in zip(rotators, angles):
                if a is not None:
                    r.move(a)
            data = ArrayWithAttrs(self.payload())
            data.attrs.update({l: r.position for l, r in self.rotators.items()})
            self.create_dataset('rotator_data_%d', data=data)

    def get_qt_ui(self):
        """Return this widget itself as its Qt UI."""
        return self


if __name__ == '__main__':
    from pyopenlab.instrument.stage.Thorlabs_ELL8K import BusDistributor
    from pyopenlab.instrument.stage.Thorlabs_ELL8K import Thorlabs_ELL8K
    bus = BusDistributor('COM6')
    ells = {l: Thorlabs_ELL8K(bus, l) for l in 'ABC'}
    rotators = Rotators(ells)
    rotators.show_gui()
