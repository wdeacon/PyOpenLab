pyopenlab
=====
Core functions and instrument scripts for the Nanophotonics lab experimental scripts.  This is designed to be one Python module, which provides both the various support functions (saving to file, running experiments in a thread, etc.) and the core instrument scripts in `pyopenlab.instruments.*`.

Experimental data is managed by the class `DataFile`, a wrapper for h5py that manages HDF5 files with auto-incrementing names and a graphical browser, which also maintains a "current" data file to which data should be saved, accessible as `pyopenlab.datafile.current()`.  For convenience, there is a function `pyopenlab.current_datafile()` that returns the same object.

Instrument scripts should be subclasses of `pyopenlab.instrument.Instrument`, though usually this is done indirectly.  Most instruments will be subclasses of either or both of a generic instrument class (defining an instrument for standard instrument types such as stages, spectrometers, etc.) and also a bus-specific class (e.g. SerialInstrument).  The `Instrument` base class takes care of a number of generic boilerplate things, such as keeping track of instances of a given class, and being able to retrieve active instances with the `instance()` and `instances()` methods.  The `pyopenlab` module also defines some decorators to make threading tasks easier, commonly used by instrument classes.


When installing:

install pyqtgraph before trying to open_browser_cmd.bat or open_browser_cmd.py
 
You can run

`pip install -r requirements.txt`

to automatically install dependencies.