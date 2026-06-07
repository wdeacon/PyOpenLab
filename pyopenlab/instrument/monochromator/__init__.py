"""Monochromator instrument drivers.

This package groups the drivers for the monochromators supported by PyOpenLab.

There is currently no shared monochromator base class; each driver inherits
directly from a generic instrument base (for example :class:`~pyopenlab.instrument.Instrument`
or :class:`~pyopenlab.instrument.serial_instrument.SerialInstrument`). Drivers
nevertheless follow a common informal interface centred on ``get_wavelength`` and
``set_wavelength``.

Available drivers:
    * :class:`~pyopenlab.instrument.monochromator.bentham_DTMc300.Bentham_DTMc300`
    * :class:`~pyopenlab.instrument.monochromator.digikrom.Digikrom`
    * :class:`~pyopenlab.instrument.monochromator.varia.Varia`
"""
