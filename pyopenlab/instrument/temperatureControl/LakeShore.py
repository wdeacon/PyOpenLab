# -*- coding: utf-8 -*-
"""Driver for Lake Shore temperature controllers."""

from pyopenlab.instrument.temperatureControl import TemperatureControlMixin
from pyopenlab.instrument.visa_instrument import VisaInstrument


class LS331(VisaInstrument, TemperatureControlMixin):
    """Lake Shore Model 331 temperature controller (VISA).

    See the `manual
    <https://www.lakeshore.com/ObsoleteAndResearchDocs/331_Manual.pdf>`_ for the
    full command reference.
    """

    def __init__(self, address, **kwargs):
        """Open a VISA connection to the controller.

        Args:
            address (str): VISA resource address of the instrument.
            **kwargs: Additional settings forwarded to
                :class:`pyopenlab.instrument.visa_instrument.VisaInstrument`.
        """
        super(LS331, self).__init__(address, **kwargs)

    def get_temperature(self):
        """Return the current temperature in Kelvin.

        Returns:
            float: The Kelvin reading from the ``KRDG?`` query, with the trailing
            terminator stripped.
        """
        reply = self.query("KRDG?")
        return float(reply[:-2])

    temperature = property(fget=get_temperature)
