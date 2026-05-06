# PyOpenLab

[PyOpenLab](https://github.com/wdeacon/PyOpenLab) is an open-source Python module designed to empower researchers and engineers through easy access to automation and control of scientific equipment. It is a scalable toolkit with plans to extend hardware support automatically through agentic AI — where an agent searches for new hardware (cameras, stages, etc.) and adds it to the library without human input.

## Key concepts

**DataFile** — a wrapper around h5py that manages HDF5 files with auto-incrementing names and a graphical browser. A "current" data file is maintained globally and accessible via `pyopenlab.current_datafile()`.

**Instrument** — all instrument scripts subclass `pyopenlab.instrument.Instrument`, usually indirectly via a type-specific base class (e.g. Camera, Stage) and/or a bus-specific class (e.g. SerialInstrument). The base class handles instance tracking; active instances can be retrieved with `instance()` and `instances()`.

## Installation

```
pip install -r requirements.txt
```

Install `pyqtgraph` before using any GUI components.
