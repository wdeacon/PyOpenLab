# -*- coding: utf-8 -*-
"""
This is a very simple script that pops up a data browser for one file.
"""

import pyopenlab.datafile
import pyopenlab.ui.hdf5_browser as browser
from pyopenlab.utils.gui import get_qt_app

if __name__ == "__main__":
    pyopenlab.datafile.set_current(r"/Users/Hera/Documents/sc922/2018-08-31.h5", mode="r")
    app = get_qt_app()
    v = browser.HDF5ItemViewer()
    v.show()
    df = pyopenlab.current_datafile()
   # v.data = df['SpectrometerSaver/measurement_0/image']
    pyopenlab.current_datafile().show_gui()
    
    #pyopenlab.current_datafile().close()