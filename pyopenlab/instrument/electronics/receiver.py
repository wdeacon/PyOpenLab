# -*- coding: utf-8 -*-
"""Standalone UDP listener that prints messages received on port 13000.

This module runs its receive loop at import time (it is meant to be executed as a
script), so importing it will block waiting for datagrams.

Note:
    Carries unfixed Python-3 bugs inherited from the original nplab code, logged
    rather than corrected here: ``recvfrom`` yields ``bytes``, but the code does
    ``"Received message: " + data`` (raises ``TypeError``) and ``data == "exit"``
    (always False, so the loop never exits cleanly).
"""

# Save as server.py
# Message Receiver
import os
import socket

host = ""
port = 13000
buf = 1024
addr = (host, port)
UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
UDPSock.bind(addr)
print("Waiting to receive messages...")
while True:
    (data, addr) = UDPSock.recvfrom(buf)
    print("Received message: " + data)
    if data == "exit":
        break
UDPSock.close()
os._exit(0)
