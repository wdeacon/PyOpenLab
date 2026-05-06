# -*- coding: utf-8 -*-
"""
This is a very simple script that pops up a data browser for one file.
"""

import pyopenlab.datafile
import pyopenlab.ui.hdf5_browser as browser
from pyopenlab.utils.gui import get_qt_app

if __name__ == "__main__":
    df = pyopenlab.current_datafile()
    df.show_gui(blocking=True)
    pyopenlab.current_datafile().close()