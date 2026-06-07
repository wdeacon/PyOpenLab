# -*- coding: utf-8 -*-
"""Driver for the Spectral Products DK240/DK480 (Digikrom) monochromator.

The Digikrom uses fixed-length serial commands with no termination character and
exchanges values as hex bytes. This driver overrides the generic serial query
machinery accordingly and exposes wavelength, grating and slit control.
"""
import numpy as np
from past.utils import old_div
import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument
from pyopenlab.utils.notified_property import NotifiedProperty


class Digikrom(SerialInstrument):
    """Spectral Products DK240/DK480 monochromator over a serial connection.

    Commands are issued as decimal values (as listed in the manual) which are
    converted to hex bytes for transmission; responses are decoded back to lists
    of decimal byte values. A status byte returned with most responses is parsed
    into :attr:`_status_byte`.

    Attributes:
        port_settings (dict): Pyserial port configuration for the instrument.
        termination_character (str): Empty, as the protocol uses fixed-length frames.
        serial_number (list[int]): Expected serial-number digits used by
            :meth:`test_communications`.
    """

    port_settings = dict(
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  #wait at most one second for a response
        writeTimeout=1,  #similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    def __init__(self, port=None, serial_number=[50, 52, 51, 49, 55]):
        """Open the connection and configure the expected serial number.

        Args:
            port (str, optional): Serial port name (e.g. ``"COM9"``). If ``None``
                the base class attempts auto-detection.
            serial_number (list[int]): Expected serial-number digits, used by
                :meth:`test_communications` to confirm the right device is attached.
        """
        self.termination_character = ''
        self.serial_number = serial_number
        super(Digikrom, self).__init__(port=port)

    def query(self,
              message,
              convert_to_hex=True,
              return_as_dec=True,
              max_len_returned=10,
              block=True):
        """Send a command and read the response, handling the fixed-length protocol.

        Overrides :meth:`SerialInstrument.query` because the Digikrom uses
        fixed-length commands with no termination character. Decimal commands are
        converted to hex for transmission and responses are decoded back to decimal.

        Args:
            message (int | list[int]): Command (or command bytes) as decimal value(s).
            convert_to_hex (bool): If ``True`` encode ``message`` to hex before sending.
            return_as_dec (bool): If ``True`` decode the response to a list of decimal
                byte values.
            max_len_returned (int): Maximum number of bytes to read; bounding this
                avoids waiting for the full serial timeout.
            block (bool): If ``True`` keep reading until the command-complete byte
                (24) is received.

        Returns:
            list[int] | bytes: Decoded decimal byte list if ``return_as_dec`` is
            ``True``, otherwise the raw bytes.
        """
        if convert_to_hex == True:
            message_hex = self.encode_bytes(message)
        else:
            message_hex = message
        self.write(message_hex)
        returned_message = self.ser.read(max_len_returned)
        if return_as_dec == True:
            returned_message = self.decode_bytes(returned_message)

        if returned_message[-1] == 24:
            block = False
            self.set_status_byte(returned_message[-2])
        elif (returned_message != [message]):
            self.set_status_byte(returned_message[-1])
            while block == True:
                block_message = self.decode_bytes(self.ser.read_all())
                if len(block_message) == 1:
                    if block_message[0] == 24:
                        block = False
        return returned_message

    @staticmethod
    def decode_bytes(byte_str):
        """Convert a raw byte response into a list of decimal values.

        Working in decimal mirrors the manual and avoids ASCII conversion mishaps.

        Args:
            byte_str: Iterable of single-character bytes returned by the device.

        Returns:
            list[int]: The ordinal (decimal) value of each byte.
        """
        decimal_list = []
        for byte in byte_str:
            decimal_list.append(ord(byte))
        return decimal_list

    @staticmethod
    def encode_bytes(decimal_list):
        """Convert decimal command value(s) into a byte string for transmission.

        Args:
            decimal_list (int | list[int]): A single decimal value or list of them.
                A scalar is wrapped in a list automatically.

        Returns:
            str: The corresponding characters, one per decimal value.
        """
        if type(decimal_list) != list:
            decimal_list = [decimal_list]
        byte_str = ''
        for decimal in decimal_list:
            byte = chr(decimal)
            byte_str += byte
        return byte_str

    def set_status_byte(self, status_byte):
        """Decode the device status byte and store it on the instrument.

        Parses the individual bits into a status dictionary (value accepted, error
        type, motor movement order, scan direction, CSR mode), logs it, and stores
        it on :attr:`_status_byte`.

        Args:
            status_byte (int): The raw status byte returned by the device.

        Note:
            The bits at index 0 and 4 are compared against the integer ``1`` rather
            than the string ``'1'`` (the byte is a string of characters here), so
            those two comparisons are always ``False``. As a result
            ``motor_movement_order`` and ``scan_direction`` never take their first
            branch. This is a latent bug; left unchanged to avoid altering behaviour.
        """
        binary_byte = bin(status_byte)[2:]
        if len(binary_byte) != 8:
            binary_byte = (8 - len(binary_byte)) * '0' + binary_byte
        if binary_byte[0] == 1:
            motor_movement_order = 'negative'
        else:
            motor_movement_order = 'positive'
        if binary_byte[4] == 1:
            scan_direction = 'positive'
        else:
            scan_direction = 'negative'
        if binary_byte[7] == '0':
            value_accepted = True
            value_error = None
        else:
            value_accepted = False
            if binary_byte[6] == '1':
                value_error = 'repeat set'
            elif binary_byte[5] == '1':
                value_error = 'value too large'
            elif binary_byte[5] == '0':
                value_error = 'value too small'
        CSR_mode = bool(int(binary_byte[2]))
        status_dict = {
            'value_accepted': value_accepted,
            'value_error': value_error,
            'motor_movement_order': motor_movement_order,
            'scan_direction': scan_direction,
            'CSR_mode': CSR_mode}

        if value_accepted == True:
            level = 'debug'
        else:
            level = 'warn'
        self.log(status_dict, level=level)
        self._status_byte = status_dict

    def get_wavelength(self):
        """Read the current centre wavelength.

        Command 29 returns the value as three bytes (high, mid, low) representing
        multiples of 65536, 256 and 1, in hundredths of a nm.

        Returns:
            float: Current wavelength in nm.
        """
        returned_message = self.query(29)
        wl = returned_message[1] * 65536
        wl += 256 * returned_message[2]
        wl += returned_message[3]
        self.set_status_byte(returned_message[-2])
        return wl / 100.0

    def set_wavelength(self, wl):
        """Set the centre wavelength.

        Command 16 expects the value as three bytes (high, mid, low) representing
        multiples of 65536, 256 and 1, in hundredths of a nm.

        Args:
            wl (float): Target wavelength in nm.
        """
        self.query(16, block=False)
        wl = wl * 100
        high_byte = int(old_div(wl, 65536))
        wl = wl - high_byte * 65536
        mid_byte = int(old_div(wl, 256))
        wl = wl - mid_byte * 256
        low_byte = int(wl)
        self.query([high_byte, mid_byte, low_byte])

    centre_wavlength = NotifiedProperty(get_wavelength, set_wavelength)

    def get_grating_id(self):
        """Read grating information from the monochromator.

        Returns:
            dict: With keys ``number_of_gratings``, ``current_grating``,
            ``grating_ruling`` (grooves/mm) and ``grating_blaze`` (nm).
        """
        info = self.query(19)
        info_dict = {
            'number_of_gratings': info[1],
            'current_grating': info[2],
            'grating_ruling': info[3] * 256 + info[4],
            'grating_blaze': info[5] * 256 + info[6]}
        return info_dict

    def set_grating(self, grating_number):
        """Select a grating, if additional gratings are installed.

        Args:
            grating_number (int): Index of the grating to select.
        """
        self.query(26)
        self.query(grating_number)

    def reset(self):
        """Return the grating to its home position."""
        self.query([255, 255, 255])

    def clear(self):
        """Restore factory calibration values for the grating and slits.

        Also performs a reset, returning the grating to its home position.
        """
        self.query(25)

    def CSR(self, bandpass_value):
        """Set the monochromator to Constant Spectral Resolution mode.

        In this mode the slit width varies throughout a scan, which is useful when
        a constant interval of frequency is desired (e.g. spectral power
        distribution measurements).

        Args:
            bandpass_value (int): Target bandpass, sent as a two-byte value.
        """
        self.query(28)
        high_byte = int(old_div(bandpass_value, 256))
        bandpass_value = bandpass_value - high_byte * 256
        low_byte = int(bandpass_value)
        self.query([high_byte, low_byte])

    def echo(self):
        """Verify communications with the DK240/480 via the ECHO command."""
        self.log(self.query(27), level='info')

    def gval(self, repositioning_wl):
        """Recalibrate the monochromator positioning scale factor.

        Should be used immediately after the ZERO command: set the monochromator to
        the peak of a known spectral line, then supply that line's position here.

        Args:
            repositioning_wl (float): Known spectral-line wavelength in nm.
        """
        self.query(18)
        repositioning_wl = repositioning_wl * 100
        high_byte = int(old_div(repositioning_wl, 65536))
        repositioning_wl = repositioning_wl - high_byte * 65536
        mid_byte = int(old_div(repositioning_wl, 256))
        repositioning_wl = repositioning_wl - mid_byte * 256
        low_byte = int(repositioning_wl)
        self.query([high_byte, mid_byte, low_byte])

    def get_serial(self):
        """Return the monochromator's serial number digits.

        Returns:
            list[int]: The serial-number digits (the payload of the response).
        """
        return self.query(33)[1:-2]

    def get_slit_widths(self):
        """Return the current slit widths in microns.

        The response is four bytes (six for the DK242): high/low byte of the
        entrance slit width, then high/low of the exit slit width, and for the
        DK242 a final high/low pair for the middle slit.

        Returns:
            numpy.ndarray: Slit widths in microns, one entry per slit.
        """
        slit_info = self.query(30)[1:-2]
        slit_info = np.array(slit_info)
        low_byte = slit_info[1::2]
        high_byte = slit_info[::2]
        slit_info = 256 * high_byte + low_byte
        return slit_info

    def set_all_slits(self, slit_width):
        """Adjust all slits to a given width.

        Args:
            slit_width (int): Target slit width in microns.
        """
        high_byte = int(old_div(slit_width, 256))
        slit_width = slit_width - high_byte * 256
        low_byte = int(slit_width)
        self.query(14)
        self.query([high_byte, low_byte])

    def set_slit_1_width(self, slit_width):
        """Adjust the entrance slit to a given width.

        Args:
            slit_width (int): Target slit width in microns.
        """
        high_byte = int(old_div(slit_width, 256))
        slit_width = slit_width - high_byte * 256
        low_byte = int(slit_width)
        self.query(31)
        self.query([high_byte, low_byte])

    def set_slit_2_width(self, slit_width):
        """Adjust the exit slit to a given width.

        Args:
            slit_width (int): Target slit width in microns.

        Note:
            A site comment recorded the exit slit as not installed (05042019).
        """
        high_byte = int(old_div(slit_width, 256))
        slit_width = slit_width - high_byte * 256
        low_byte = int(slit_width)
        self.query(32)
        self.query([high_byte, low_byte])

    def set_slit_3_width(self, slit_width):
        """Adjust the middle slit to a given width.

        Args:
            slit_width (int): Target slit width in microns.
        """
        high_byte = int(old_div(slit_width, 256))
        slit_width = slit_width - high_byte * 256
        low_byte = int(slit_width)
        self.query(34)
        self.query([high_byte, low_byte])

    def test_communications(self):
        """Check that the expected Digikrom is on the other end of the COM port.

        Returns:
            bool: ``True`` if the device's serial number matches
            :attr:`serial_number`, ``False`` on mismatch or communication failure.
        """
        try:
            serial_num = self.get_serial()
        except:
            return False
        if serial_num == self.serial_number:
            return True
        else:
            return False


def init():
    """Convenience constructor for a Digikrom on the default lab port (COM9).

    Returns:
        Digikrom: An initialised instrument instance.
    """
    spec = Digikrom(port="COM9", serial_number=[50, 52, 51, 49, 55])
    return spec


if __name__ == '__main__':
    spec = Digikrom(serial_number=[50, 52, 51, 49, 55])
    print(spec)
    # spec.set_wavelength(0)
    wavel = spec.get_wavelength()
    print(wavel)
    slit = spec.get_slit_widths()
    print(slit)
