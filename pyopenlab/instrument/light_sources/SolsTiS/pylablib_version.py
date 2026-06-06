# -*- coding: utf-8 -*-
"""Example of connecting to a SolsTiS via pylablib's ``M2.Solstis`` driver."""

import socket

from pylablib.devices import M2

if __name__ == '__main__':

    address = ('172.24.37.153', 39933)
    laser = M2.Solstis(*address)
# laser.close()
