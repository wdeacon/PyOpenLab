"""VISA instrument communication for pyopenlab."""

from functools import partial

import pyvisa as visa

from pyopenlab.instrument.message_bus_instrument import MessageBusInstrument
from pyopenlab.instrument.message_bus_instrument import queried_channel_property
from pyopenlab.instrument.message_bus_instrument import queried_property


class VisaInstrument(MessageBusInstrument):
    """Base class for instruments communicating over VISA (GPIB, USB, TCP/IP, etc.).

    Wraps a pyvisa Resource with the pyopenlab MessageBusInstrument interface
    and thread-safe locking. Pass the VISA address string to the constructor.

    Attributes:
        idn: Instrument identification string, queried via ``*IDN?``.
    """

    def __init__(self, address, settings=None):
        """Open a VISA resource.

        Args:
            address: VISA resource string (e.g. ``'GPIB0::7::INSTR'`` or
                ``'USB0::0x1234::0x5678::SN001::INSTR'``).
            settings: Optional dict of pyvisa resource settings —
                ``read_termination``, ``write_termination``, ``timeout``
                (0 for infinite), ``send_end``, ``delay`` (seconds between
                write and read in a query).

        Raises:
            AssertionError: If ``address`` is not among available VISA
                resources (available resources are printed and execution
                continues).
        """
        super(VisaInstrument, self).__init__()
        rm = visa.ResourceManager()
        try:
            assert address in rm.list_resources(), "The instrument was not found"
        except AssertionError:
            print('Available equipment:', rm.list_resources())
        if settings is None:
            settings = dict()
        self.instr = rm.open_resource(address, **settings)
        self._address = address
        self._settings = settings

    def __del__(self):
        """Close the VISA resource on garbage collection."""
        try:
            self.instr.close()
        except Exception as e:
            print("The VISA resource didn't close cleanly:", e)

    def _write(self, *args, **kwargs):
        """Write a message to the instrument.

        Args:
            *args: Forwarded to ``pyvisa.Resource.write``.
            **kwargs: Forwarded to ``pyvisa.Resource.write``.

        Returns:
            tuple: ``(bytes_written, status_code)`` as returned by pyvisa.
        """
        with self.communications_lock:
            return self.instr.write(*args, **kwargs)

    def read(self, *args, **kwargs):
        """Read a response from the instrument.

        Args:
            *args: Forwarded to ``pyvisa.Resource.read``.
            **kwargs: Forwarded to ``pyvisa.Resource.read``.

        Returns:
            str: The response string.
        """
        with self.communications_lock:
            return self.instr.read(*args, **kwargs)

    def query(self, *args, **kwargs):
        """Write a message and read the response in one call.

        Args:
            *args: Forwarded to ``pyvisa.Resource.query``.
            **kwargs: Forwarded to ``pyvisa.Resource.query``.

        Returns:
            str: The response string.
        """
        with self.communications_lock:
            return self.instr.query(*args, **kwargs)

    def clear_read_buffer(self):
        """Drain the instrument's read buffer by reading until an exception occurs."""
        empty_buffer = False
        while not empty_buffer:
            try:
                self.instr.read()
            except Exception:
                print("Buffer emptied")
                empty_buffer = True

    idn = queried_property('*idn?', dtype='str')


if __name__ == '__main__':
    instrument = VisaInstrument(address='GPIB0::7::INSTR')
    print(instrument.query('*idn?'))
    print(instrument.idn)
    print(instrument.float_query)
