# -*- coding: utf-8 -*-
"""UDP messaging instrument for triggering acquisition on a remote computer."""

# Save as server.py
# Message Receiver
import socket

from pyopenlab.instrument import Instrument


class Talk2Computer(Instrument):
    """Send and receive UDP control messages to/from another computer.

    Note:
        This class carries several unfixed runtime bugs inherited from the
        original nplab code (logged for later repair, not corrected here):

        - :meth:`receive` reads ``bytes`` from the socket then does
          ``"Received message: " + data`` and ``data == "exit"``, which raise a
          ``TypeError`` / always compare unequal under Python 3 (bytes vs str).
          ``return data`` also precedes ``UDPSock.close()``, so the socket is never
          closed, and the ``while`` loop always breaks on the first datagram.
        - :meth:`send` and :meth:`send_particle_number` are declared without
          ``self`` and so are not callable as bound methods on an instance.
        - :meth:`send_particle_number` references undefined names ``wizard``, the
          module-level ``send`` (the method shadows it), and ``exception`` (lower
          case), so it cannot run as written.
    """

    def receive(self):
        """Bind a UDP socket and block until a message arrives.

        Returns:
            The raw datagram received on UDP port 65535.

        Note:
            See the class docstring; the bytes/str handling and control flow here
            are broken under Python 3 and were intentionally left unfixed.
        """
        host = ""
        port = 65535
        buf = 1024
        addr = (host, port)
        UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        UDPSock.bind(addr)

        print("Waiting to receive messages...")
        while True:
            #(data, addr) = UDPSock.recvfrom(buf)
            data = UDPSock.recv(buf)
            print("Received message: " + data)
            if data == "exit":
                break
            if data != " ":
                break
        return data
        UDPSock.close()
        #os._exit(0)


#    def send(self, ipadd = "172.24.36.227", displaymsg = " "): # set to IP address of target computer
#        port = 65535
#        addr = (ipadd, port)
#        data = " "
#        UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#        while True:
#            if displaymsg == " ":
#                data = raw_input("Enter message to send or type 'exit': ")
#                UDPSock.sendto(data, addr)
#            else:
#                UDPSock.sendto(str(displaymsg), addr)
#                break
#            if data == "exit":
#                break
#        UDPSock.close()

    def send_particle_number(pretext="Particle_", offset=0):
        """Send a start command tagged with the current particle number.

        Args:
            pretext: Filename prefix prepended to the particle number.
            offset: Integer added to the current particle index before sending.

        Note:
            Non-functional as written (see class docstring): missing ``self`` and
            references to undefined ``wizard``, ``send`` and ``exception``.
        """
        try:
            current_particle = wizard.current_particle
            particle_name = pretext + str(current_particle + offset)
            send("172.24.36.227", {'cmd': 'start', 'filename': particle_name})
        except exception as e:
            print(e)

    def send(ipadd="172.24.36.227",
             dict={
                 'cmd': 'start',
                 'filename': 'np1'}):  # set to IP address of target computer
        """Send a single UDP command dict to the target computer.

        Args:
            ipadd: IP address of the target computer.
            dict: Command payload; its ``str()`` is sent as one UDP datagram.

        Note:
            Declared without ``self`` (see class docstring), so it is not usable as
            a bound method.
        """
        port = 65535
        addr = (ipadd, port)
        data = " "
        UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        UDPSock.sendto(str(dict), addr)
        UDPSock.close()

    def send2(self,
              ipadd="172.24.36.227",
              dict={
                  'cmd': 'start',
                  'filename': 'np1'}):  # set to IP address of target computer
        """Send a single UDP command dict to the target computer (bound-method form).

        Args:
            ipadd: IP address of the target computer.
            dict: Command payload; its ``str()`` is sent as one UDP datagram.
        """
        port = 65535
        addr = (ipadd, port)
        data = " "
        UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while True:
            UDPSock.sendto(str(dict), addr)
            break
            if data == "exit":
                break
        UDPSock.close()
        #os._exit(0)
