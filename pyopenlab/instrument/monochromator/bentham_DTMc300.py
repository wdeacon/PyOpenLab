"""Driver for the Bentham DTMc300 double monochromator.

Control is provided through the manufacturer's Windows DLL (``benhw32_fastcall.dll``),
loaded via :mod:`ctypes`. Token names used by the DLL ``BI_get``/``BI_set`` API are
mapped to their integer values by reading ``bentham_dlltokens.h`` at import time.
"""

import ctypes
from ctypes import ARRAY
from ctypes import byref
from ctypes import c_char
from ctypes import c_char_p
from ctypes import CDLL
from ctypes import POINTER
from ctypes import WinDLL
import os
import time

import numpy as np

from pyopenlab.instrument import Instrument

FILEPATH = os.path.realpath(__file__)
DIRPATH = os.path.dirname(FILEPATH)

ATTRS_PATH = "{0}\\{1}".format(DIRPATH, "bentham_DTMc300_attributes.atr")
CONFIG_PATH = "{0}\\{1}".format(DIRPATH, "bentham_DTMc300_config.cfg")
DLL_PATH = "{0}\\{1}".format(DIRPATH, "bentham_instruments_dlls\\Win32\\benhw32_fastcall.dll")


def read_tokens():
    """Build the DLL token-name to integer mapping.

    The Bentham DLL identifies settings by integer tokens whose symbolic names are
    defined as ``#define`` directives in ``bentham_dlltokens.h``. This parses that
    header and returns the mapping.

    Returns:
        dict[str, int]: Mapping from token name to its integer value.
    """
    token_map = {}
    import re
    definition_pattern = re.compile("#define.*")
    token_filepath = os.path.normpath(DIRPATH + "/bentham_dlltokens.h")
    with open(token_filepath, "r") as f:
        for line in f.readlines():
            line = line.strip("\n")
            if bool(definition_pattern.match(line)) == True:
                line_list = line.split(" ")
                token_map.update({line_list[1]: int(line_list[2])})

    return token_map


class Bentham_DTMc300(Instrument):
    """Bentham DTMc300 double monochromator controlled via the manufacturer DLL.

    On construction the driver loads the DLL, builds the system model from the
    bundled config/attribute files, initialises the hardware and parks it.

    Note:
        The DLL string-argument calls (e.g. ``c_char_p("")`` in ``__init__`` and
        ``c_char_p(item_id)``) pass ``str`` objects. Under Python 3 ``ctypes``
        requires ``bytes`` for ``c_char_p``, so these calls will raise
        ``TypeError`` until the strings are encoded; this driver has not been
        verified on Python 3.

    Attributes:
        dll: Loaded ``WinDLL`` handle to ``benhw32_fastcall.dll``.
        token_map (dict[str, int]): Token-name to integer mapping (see
            :func:`read_tokens`).
        components (list[str]): Hardware component identifiers reported by the DLL.
    """

    def __init__(self):
        super(Bentham_DTMc300, self).__init__()

        self.dll = WinDLL(DLL_PATH)

        self.token_map = read_tokens()
        error_report = c_char_p("")
        response = self.dll.BI_build_system_model(c_char_p(CONFIG_PATH), error_report)
        print("Error report", error_report)
        print("BI_build_system_model:", response)
        response = self.dll.BI_load_setup(c_char_p(ATTRS_PATH))
        print("BI_load_setup:", response)
        response = self.dll.BI_initialise(None)
        print("BI_initialise:", response)
        response = self.dll.BI_park(None)
        print("BI_park:", response)

        self.components = self.get_component_list()

    def get_component_list(self):
        """Query the DLL for the list of installed hardware components.

        Returns:
            list[str]: Component identifiers, with empty entries stripped.
        """
        mylist = (ctypes.c_char * 100)()
        response = self.dll.BI_get_component_list(ctypes.byref(mylist))
        components = [
            k for k in ("".join([c for c in mylist if c != '\x00'])).split(",") if k != '']
        print("BI_get_component_list:", response, components)
        return components

    def get(self, item_id, token, index):
        """Read a single floating-point parameter from a hardware component.

        Args:
            item_id (str): Component identifier (e.g. ``"mono"``).
            token (str): Token name to look up in :attr:`token_map`.
            index (int): Parameter index for the token.

        Returns:
            float: The value reported by the DLL.
        """
        value = ctypes.c_double(0.0)
        print("id:{0}, token:{1}, index:{2}".format(item_id, token, index))
        response = self.dll.BI_get(c_char_p(item_id), ctypes.c_int32(self.token_map[token]),
                                   ctypes.c_int32(index), ctypes.byref(value))
        print("BI_get", response)
        return value.value

    def get_wavelength(self, token="mono"):
        """Return the monochromator's current wavelength.

        Args:
            token (str): Unused; retained for call-signature compatibility. The
                read is always performed against the ``"mono"`` component.

        Returns:
            float: Current wavelength in nm.
        """
        wavelength = self.get(item_id="mono", token="MonochromatorCurrentWL", index=0)
        return wavelength

    def set_wavelength(self, wavelength):
        """Move the monochromator to a target wavelength.

        Blocks for 300 ms after issuing the move to allow the hardware to settle.

        Args:
            wavelength (float): Target wavelength in nm.
        """
        delay = ctypes.c_double(0.0)
        response = self.dll.BI_select_wavelength(ctypes.c_double(wavelength), ctypes.byref(delay))
        time.sleep(0.3)  # Allow the grating drive to finish moving before returning.
        return


if __name__ == "__main__":

    m = Bentham_DTMc300()
    initial = m.get_wavelength()
    m.set_wavelength(0)
    final = m.get_wavelength()
    print("Initial, Final:", initial, final)
    print("DONE")
