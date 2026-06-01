"""Serial instrument communication for pyopenlab."""
import threading
import time

import serial
from serial import EIGHTBITS
from serial import FIVEBITS
from serial import PARITY_EVEN
from serial import PARITY_MARK
from serial import PARITY_NONE
from serial import PARITY_ODD
from serial import PARITY_SPACE
from serial import SEVENBITS
from serial import SIXBITS
from serial import STOPBITS_ONE
from serial import STOPBITS_ONE_POINT_FIVE
from serial import STOPBITS_TWO
import serial.tools.list_ports

from pyopenlab.instrument.message_bus_instrument import MessageBusInstrument


class SerialInstrument(MessageBusInstrument):
    """Base class for instruments communicating over a serial port.

    Subclass this and set ``port_settings`` to a dict of pyserial kwargs.
    Override :meth:`test_communications` to validate the connection on open.

    Attributes:
        port_settings: Dict of keyword arguments passed directly to
            ``serial.Serial``. Common keys:

            - ``baudrate`` — e.g. 9600 or 115200
            - ``bytesize`` — ``FIVEBITS``, ``SIXBITS``, ``SEVENBITS``,
              or ``EIGHTBITS``
            - ``parity`` — ``PARITY_NONE``, ``PARITY_EVEN``, ``PARITY_ODD``,
              ``PARITY_MARK``, or ``PARITY_SPACE``
            - ``stopbits`` — ``STOPBITS_ONE``, ``STOPBITS_ONE_POINT_FIVE``,
              or ``STOPBITS_TWO``
            - ``timeout`` — read timeout in seconds
            - ``xonxoff`` — enable software flow control
            - ``rtscts`` — enable hardware RTS/CTS flow control
            - ``dsrdtr`` — enable hardware DSR/DTR flow control
        initial_character: String prepended to every outgoing message.
    """
    port_settings = {}
    initial_character = ''

    _serial_port_lock = threading.Lock()

    def __init__(self, port=None):
        """Open the serial port.

        Args:
            port: Port name (e.g. ``'COM3'`` or ``'/dev/ttyUSB0'``). If None,
                autodetection is attempted via :meth:`find_port`.
        """
        MessageBusInstrument.__init__(
            self)  # Using super() here can cause issues with multiple inheritance.
        # Eventually this shouldn't rely on init...
        if self.termination_read is None:
            self.termination_read = self.termination_character
        self.open(port, False)

    @property
    def timeout(self):
        """Serial port read timeout in seconds."""
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self.ser._timeout = self._timeout = value
        self.ser._reconfigure_port()

    def open(self, port=None, quiet=True):
        """Open communications with the serial port.

        Args:
            port: Port name to open. If None, autodetection is attempted via
                :meth:`find_port`.
            quiet: If True (default), suppress the warning when opening an
                already-open port.

        Raises:
            AssertionError: If no port can be found or the instrument does not
                respond to :meth:`test_communications`.
        """
        with self.communications_lock:
            if hasattr(self, 'ser') and self.ser.isOpen():
                if not quiet:
                    print("Warning: attempted to open an already-open port!")
                return
            if port is None:
                port = self.find_port()
            assert port is not None, "We don't have a serial port to open, meaning you didn't specify a valid port and autodetection failed.  Are you sure the instrument is connected?"
            self.ser = serial.Serial(port, **self.port_settings)
            # self.ser_io = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser,1),
            #                                newline = self.termination_character,
            #                                line_buffering = True)
            # the block above wraps the serial IO layer with a text IO layer
            # this allows us to read/write in neat lines.  NB the buffer size must
            # be set to 1 byte for maximum responsiveness.
            assert self.test_communications(
            ), "The instrument doesn't seem to be responding.  Did you specify the right port?"

    def close(self):
        """Release the serial port"""
        with self.communications_lock:
            try:
                self.ser.close()
            except Exception as e:
                print("The serial port didn't close cleanly:", e)

    def __del__(self):
        self.close()

    def _write(self, query_string, ignore_echo=False, timeout=None):
        """Write a string to the serial port.

        Args:
            query_string: The string to send, wrapped with ``initial_character``
                and ``termination_character``.
            ignore_echo: If True, flush the input buffer before writing and
                discard the echoed response afterward.
            timeout: Read timeout in seconds used when reading the echo.
        """
        assert self.ser.isOpen(
        ), "Warning: attempted to write to the serial port before it was opened.  Perhaps you need to call the 'open' method first?"
        try:
            if self.ser.outWaiting() > 0:
                self.ser.flushOutput()  # ensure there's nothing waiting
        except AttributeError:
            if self.ser.out_waiting > 0:
                self.ser.flushOutput()  # ensure there's nothing waiting
        if ignore_echo:
            self.flush_input_buffer()
        self.ser.write(
            str.encode(self.initial_character + str(query_string) + self.termination_character))
        if ignore_echo:
            echo = self.readline(timeout).strip()
            if query_string != echo:
                self._logger.warn('This write did not echo: ' + echo)

    def flush_input_buffer(self):
        """Make sure there's nothing waiting to be read, and clear the buffer if there is."""
        with self.communications_lock:
            self.ser.reset_input_buffer()
            # if self.ser.inWaiting() > 0: self.ser.flushInput()
    def flush_output_buffer(self):
        """Make sure there's nothing waiting to be written, and clear the buffer if there is."""
        with self.communications_lock:
            self.ser.reset_output_buffer()

    def readline(self, timeout=None):
        """Read a line from the serial port, blocking until the termination character arrives.

        Args:
            timeout: Maximum time to wait in seconds. Defaults to
                ``self.timeout`` if set, otherwise 10 seconds.

        Returns:
            str: The received line with the termination character replaced by
            ``'\\n'``.
        """
        with self.communications_lock:
            if hasattr(self, 'timeout') and timeout is None:
                timeout = self.timeout
            elif timeout is None:
                timeout = 10
            eol = str.encode(self.termination_character)
            leneol = len(eol)
            line = bytearray()
            start = time.time()
            while time.time() - start < timeout:
                c = self.ser.read(1)
                if c:
                    line += c
                    if line[-leneol:] == eol:
                        break
                else:
                    break
            return line.decode().replace(self.termination_read, '\n')

    def test_communications(self):
        """Check whether the instrument is responding on the current port.

        Override in subclasses to send a command and verify a known reply.
        The base implementation always returns True.

        Returns:
            bool: True if the instrument is responding, False otherwise.
        """
        with self.communications_lock:
            return True

    def find_port(self):
        """Scan available serial ports and return the first one that responds.

        Calls :meth:`open` and :meth:`test_communications` on each port in turn.

        Returns:
            str | None: The port name if found, otherwise None.
        """
        with self.communications_lock:
            success = False
            for port_name, _, _ in serial.tools.list_ports.comports(
            ):  # loop through serial ports, apparently 256 is the limit?!
                try:
                    print("Trying port", port_name)
                    self.open(port_name)
                    success = True
                    print("Success!")
                except:
                    pass
                finally:
                    try:
                        self.close()
                    except:
                        pass  # we don't care if there's an error closing the port...
                if success:
                    break  # again, make sure this happens *after* closing the port
            if success:
                return port_name
            else:
                return None
