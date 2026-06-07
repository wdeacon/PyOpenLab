# -*- coding: utf-8 -*-
"""Driver for the Fianium SuperChrome filter via GUI automation of its vendor app.

Instead of talking to the SDK directly, :class:`SuperChromeUIAuto` drives the vendor
``SuperChromeTest.exe`` dialog with ``pywinauto`` to select filters, move them in and
out of the beam, and set positions or cut-off wavelengths.
"""

import numpy as np
from pywinauto.application import Application


class SuperChromeUIAuto(object):
    """Controls a Fianium SuperChrome filter by automating the vendor test GUI."""

    def __init__(self):
        """Connect to the running ``SuperChromeTest.exe`` and grab its filter dialog."""
        self.filter_app = Application().connect(
            path=r"C:\Program Files (x86)\Fianium\SuperChrome\SuperChromeTest.exe")
        self.filter_diag = self.filter_app.TestDualVariableFilter

    def select_filter(self, filter_str):
        """Select a filter in the dialog and move it into the beam path.

        Args:
            filter_str (str): Filter name, case-insensitive ``'filter1'`` or ``'filter2'``.
                Any other value is silently ignored.
        """

        if filter_str.lower() == 'filter1':
            self.filter_diag.Filter1.click()
            self.filter_diag.InBeamPath.click()
        else:
            if filter_str.lower() == 'filter2':
                self.filter_diag.Filter2.click()
                self.filter_diag.InBeamPath.click()

    def move_filter_pos(self, filter_str='Filter2', filter_pos=5800):
        """Move a filter to a raw position value and apply the change.

        Args:
            filter_str (str): Filter name, ``'filter1'`` or ``'filter2'`` (case-insensitive).
            filter_pos (int): Raw position value entered into the dialog.

        Note:
            On an invalid filter name this calls ``display(...)``, which is not imported
            anywhere in this module and will raise ``NameError``.
        """

        if filter_str.lower() == 'filter1' or filter_str.lower() == 'filter2':
            self.select_filter(filter_str)
            self.filter_diag.Edit6.type_keys(str(filter_pos))
            self.filter_diag.Apply.click()
        else:
            display('Invalid filter name')

    def move_out_of_beam(self, filter_str='Filter2'):
        """Move a filter out of the beam path and apply the change.

        Args:
            filter_str (str): Filter name, ``'filter1'`` or ``'filter2'`` (case-insensitive).

        Note:
            On an invalid filter name this calls the undefined ``display(...)`` helper
            (see :meth:`move_filter_pos`).
        """

        if filter_str.lower() == 'filter1':
            self.filter_diag.Filter1.click()
            self.filter_diag.OutBeamPath.click()
            self.filter_diag.Apply.click()

        else:
            if filter_str.lower() == 'filter2':
                self.filter_diag.Filter2.click()
                self.filter_diag.OutBeamPath.click()
                self.filter_diag.Apply.click()
            else:
                display('Invalid filter name')

    def move_filter_wavelength(self, filter_str='Filter2', cut_off=650):
        """Move a filter to the position matching a cut-off wavelength via a lookup table.

        Args:
            filter_str (str): Filter name. Only ``'filter2'`` is calibrated; ``'filter1'``
                is rejected.
            cut_off (float): Desired cut-off wavelength, in nm.

        Note:
            The lookup table path is hard-coded to a Cambridge-specific OneDrive location
            and must be edited for other machines. The ``'filter1'`` branch calls the
            undefined ``display(...)`` helper (see :meth:`move_filter_pos`).
        """

        if filter_str.lower() == 'filter2':
            self.lookup_table = np.loadtxt(
                r'E:\OneDrive - University Of Cambridge\Ultrafast Raman Rig\fo263\filter2_lookup_table.txt'
            )
        if filter_str.lower() == 'filter1':
            display('Filter1 is not yet calibrated. Sorry!')
            return

        # argmin() returns an int index and the divisor is the int 2, so integer division
        # preserves the original old_div(int, int) semantics.
        filter_pos = np.abs(self.lookup_table - cut_off).argmin() // 2
        self.move_filter_pos(filter_str, self.lookup_table[int(filter_pos)][0])
