# -*- coding: utf-8 -*-
"""Base serial driver for Thorlabs APT virtual COM port devices.

Provides :class:`APT_VCP`, which implements the fixed-length binary APT protocol
shared by Thorlabs motor controllers, flippers and similar hardware, plus
:func:`detect_APT_VCP_devices` for discovering connected units.
"""
from collections import deque
import struct
import time

import serial
import serial.tools.list_ports as list_ports

import pyopenlab.instrument.serial_instrument as serial_instrument


def detect_APT_VCP_devices():
    """Scan all serial ports for APT devices.

    Tries each known destination address on every COM port and records those
    that respond.

    Returns:
        dict: Maps each port name to a dict with ``destination``,
        ``Serial Number`` and ``Model`` for the device found there.
    """
    possible_destinations = [0x50, 0x11, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A]
    device_dict = dict()
    for port_name, _, _ in list_ports.comports(
    ):  # loop through serial ports, apparently 256 is the limit?!

        print("Trying port", port_name)
        try:
            for destination in possible_destinations:
                try:
                    test_device = APT_VCP(port_name, destination=destination)
                    device_dict[port_name] = {
                        'destination': destination,
                        'Serial Number': test_device.serial_number,
                        'Model': test_device.model}
                    break
                except struct.error:
                    pass
        except serial.serialutil.SerialException:
            pass
    return device_dict


class APT_VCP(serial_instrument.SerialInstrument):
    """Base driver for the APT virtual COM port binary protocol.

    Handles the fixed-length message framing, channel/state encoding and
    hardware discovery common to Thorlabs APT devices. Device-specific
    subclasses must implement :meth:`get_status_update` and :meth:`update_status`.
    """
    port_settings = dict(baudrate=115200,
                         bytesize=8,
                         parity=serial.PARITY_NONE,
                         stopbits=1,
                         xonxoff=0,
                         rtscts=0,
                         timeout=1,
                         writeTimeout=1)
    termination_character = ""  # The APT communicates via fixed length messages therefore this is not required
    surprise_message_codes = {
        'MGMSG_HW_RESPONSE': 0x0080,
        # The message id codes for messages sent from the hardware to the device.
        'MGMSG_HW_RICHRESPONSE': 0x0081,
        # One for one line error code and one for longer error codes
        'Status update id': None
    }  # This is the satus update message id that varies for each device and therefore must be set

    channel_number_to_identity = {
        1: 0x01,
        2: 0x02,
        3: 0x04,
        4: 0x08}  # Sets up the channel numbers to values
    state_conversion = {
        True: 0x01,
        False: 0x02
    }  # Sets up the conversion from True and False values to 1's and 2's (godknows why they havnt used 0 and 1)
    reverse_state_conversion = {0x01: True, 0x02: False}
    serial_num_to_device_types = {
        0: ['Filter flipper', 'MFF002'],
        20: ['Legacy Single channel stepper driver', 'BSC001'],
        25: ['Legacy single channel mini stepper driver', 'BMS001'],
        27: ['K - Cube brushed DC servo driver', 'KDCT101'],
        28: ['K - Cube brushless DC servo driver', 'KBD101'],
        30: ['Legacy dual channel stepper driver', 'BSC002'],
        35: ['Legacy dual channel mini stepper driver', 'BMS002'],
        40: ['Single channel stepper driver', 'BSC101'],
        60: ['OptoSTDriver(mini stepper driver)', 'OST001'],
        63: ['OptoDCDriver (mini DC servo driver)', 'ODC001'],
        70: ['Three channel card slot stepper driver', 'BSC103'],
        80: ['Stepper Driver T-Cube', 'TST001'],
        83: ['DC Driver T-Cube', 'TDC001'],
        73: ['Brushless DC motherboard', 'BBD102/BBD103'],
        94: ['Brushless DC motor card', 'BBD102/BBD103']}
    command_log = deque(maxlen=20)  # stores commands sent to the device
    timeout = 30

    def __init__(self,
                 port=None,
                 source=0x01,
                 destination=None,
                 use_si_units=False,
                 stay_alive=False):
        """Open the serial port and read the device's hardware info.

        Args:
            port: Serial port name. ``None`` triggers interactive selection by
                the base ``SerialInstrument``.
            source: Source address for outgoing messages.
            destination: Destination address, or a dict mapping channel keys to
                addresses. Logged as an error if ``None``.
            use_si_units: Reserved for subclasses that convert device units to
                SI units.
            stay_alive: If True, periodically send keep-alive messages so the
                controller does not assume the PC has crashed.
        """
        serial_instrument.SerialInstrument.__init__(self, port=port)  # this opens the port
        self.source = source
        if destination is None:
            self._logger.error('destination has not been set!')
        elif type(destination) != dict:
            self.destination = {'1': destination}
        else:
            self.destination = destination
        self.stay_alive = stay_alive
        self.serial_number = None
        self.model = None
        self.number_of_channels = None
        hrdwr_info = self.get_hardware_info(
        )  # sets things like the serial_number, model and number_of_channels
        self._logger.debug(hrdwr_info)

    @staticmethod
    def unpack_binary_mask(value, size=13):
        """Unpack an integer into a list of booleans, one per bit.

        Args:
            value: The integer to unpack.
            size: Number of bits to extract.

        Returns:
            list[bool]: The bits of ``value``, least-significant first.
        """
        lst = [bool(value & (1 << size - i - 1)) for i in range(size)]
        lst.reverse()
        return lst

    @staticmethod
    def _bit_mask_array(value, bit_mask):
        """Test ``value`` against each entry of ``bit_mask``.

        Args:
            value: The integer to test.
            bit_mask: Iterable of bit masks to AND against ``value``.

        Returns:
            list[bool]: One boolean per mask, True where the bit is set.
        """
        final_mask = []
        for mask in bit_mask:
            final_mask += [bool(value & int(mask))]
        return final_mask

    def read(self):
        """Read one APT message, handling extra data streams and error codes.

        Reads the 6-byte header, then any trailing data block, recursing past
        hardware response/keep-alive messages until a normal reply is reached.

        Returns:
            dict: The decoded message (ids, source/destination and any
            ``data``), or ``None`` for an intercepted surprise message whose
            real reply is handled by the recursive call.
        """
        header = bytearray(self.ser.read(6))  # read 6 byte header
        msgid, length, dest, source = struct.unpack(
            '<HHBB', header
        )  # unpack the header as described by the format were a second data stream is expected
        if msgid in list(self.surprise_message_codes.values()
                         ):  # Compare the message code to the list of suprise message codes
            if msgid == self.surprise_message_codes['MGMSG_HW_RESPONSE']:
                msgid, param1, param2, dest, source = struct.unpack('<HBBBB', header)
                returned_message = {
                    'message': msgid,
                    'param1': param1,
                    'param2': param2,
                    'dest': dest,
                    'source': source}
                self._logger.debug(returned_message)
                self.read()
            elif msgid == self.surprise_message_codes['MGMSG_HW_RICHRESPONSE']:
                data = self.ser.read(length)
                returned_message = {
                    'message': msgid,
                    'length': length,
                    'dest': dest,
                    'source': source,
                    'data': data}
                self._logger.debug(returned_message)
                self.read()
            elif (msgid == self.surprise_message_codes['Status update id'] and
                  self.command_log[-1] == self.surprise_message_codes['Status update id']):
                data = self.ser.read(length)
                returned_message = {
                    'message': msgid,
                    'length': length,
                    'dest': dest,
                    'source': source,
                    'data': data}
                self.update_status(returned_message)
                self.read()
        else:
            if self.source | 0x80 == dest:
                data = self.ser.read(length)
                returned_message = {
                    'message': msgid,
                    'length': length,
                    'dest': dest,
                    'source': source,
                    'data': data}
            elif self.source != dest:
                if dest <= 0x80:
                    self.source = dest
                else:
                    self.source = dest - 128
                data = self.ser.read(length)
                returned_message = {
                    'message': msgid,
                    'length': length,
                    'dest': dest,
                    'source': source,
                    'data': data}
            else:
                msgid, param1, param2, dest, source = struct.unpack('<HBBBB', header)

                returned_message = {
                    'message': msgid,
                    'param1': param1,
                    'param2': param2,
                    'dest': dest,
                    'source': source}
            return returned_message

    def _write(self, message_id, param1=0x00, param2=0x00, data=None, destination_id=None):
        """Frame and send an APT message.

        Combines the message id, two parameters (or a data block) and the
        source/destination addresses into a binary packet. Sends a keep-alive
        first if the command log is full and ``stay_alive`` is set.

        Args:
            message_id: APT message id to send.
            param1: First message parameter (overwritten by data length when
                ``data`` is given).
            param2: Second message parameter.
            data: Optional payload bytes for a long-form message.
            destination_id: Key into :attr:`destination`; defaults to the first
                destination.
        """
        if destination_id is None:
            destination = list(self.destination.values())[0]
        else:
            destination = self.destination[destination_id]
        if data is None:
            formated_message = bytearray(
                struct.pack('<HBBBB', message_id, param1, param2, destination, self.source))
        else:
            param1 = len(data)
            formated_message = bytearray(
                struct.pack('<HBBBB', message_id, param1, param2, destination | 0x80, self.source))
            formated_message += data

        if len(self.command_log) == self.command_log.maxlen \
                and 0x0492 not in self.command_log \
                and self.stay_alive:
            self.command_log.append(0x0492)
            self.staying_alive()
        self.command_log.append(message_id)
        self.ser.write(formated_message)

    write = _write

    def query(self,
              message_id,
              param1=0x00,
              param2=0x00,
              data=None,
              destination_id=None,
              blocking=False):
        """Send a message and read the reply.

        Args:
            message_id: APT message id to send.
            param1: First message parameter.
            param2: Second message parameter.
            data: Optional payload bytes.
            destination_id: Key into :attr:`destination`.
            blocking: If True, wait (up to :attr:`timeout`) for a reply via
                :meth:`_waitForReply`; otherwise read once.

        Returns:
            dict: The decoded reply message.
        """
        with self.communications_lock:
            self.flush_input_buffer()
            self._write(message_id, param1, param2, data=data, destination_id=destination_id)
            time.sleep(0.1)
            if blocking:
                reply = self._waitForReply()
                if reply[0]:
                    return reply[1]
                else:
                    self._logger.error('No reply received for message ' + str(message_id))
                    return reply[1]
            else:
                return self.read()  # question: should we strip the final newline?

    # Listing General control message, not all of these can be used with every piece of equipment
    def identify(self):
        """Instruct hardware unit to identify itself by flashing its LED"""
        self.write(0x0223)

    def set_channel_state(self, channel_number, new_state, destination_id=None):
        """Enable or disable a channel.

        Args:
            channel_number: 1-based channel number.
            new_state: ``True`` to enable, ``False`` to disable.
            destination_id: Key into :attr:`destination`.
        """
        channel_identity = self.channel_number_to_identity[channel_number]
        new_state = self.state_conversion[new_state]
        self.write(0x0210, param1=channel_identity, param2=new_state, destination_id=destination_id)

    def get_channel_state(self, channel_number, destination_id=None):
        """Get the current state of a channel.

        Args:
            channel_number: 1-based channel number.
            destination_id: Key into :attr:`destination`.

        Returns:
            bool: ``True`` if the channel is enabled, ``False`` otherwise.
        """
        message_dict = self.query(
            0x0211,
            param1=self.channel_number_to_identity[channel_number],
            destination_id=destination_id)  # Get the entire message dictionary
        current_state = self.reverse_state_conversion[message_dict[
            'param2']]  # pull out the current state parameter and convert it to a True/False value
        return current_state

    def disconnect(self, destination_id=None):
        """Disconnect the controller from the USB bus.

        Args:
            destination_id: Key into :attr:`destination`.
        """
        self.write(0x002, destination_id=destination_id)

    def enable_updates(self, enable_state, update_rate=10, destination_id=None):
        """Enable or disable periodic hardware status updates.

        Args:
            enable_state: ``True`` to start updates, ``False`` to stop them.
            update_rate: Update rate (in device units) when enabling.
            destination_id: Key into :attr:`destination`.
        """
        if enable_state:
            self.write(0x0011, param1=update_rate, destination_id=destination_id)
        else:
            self.write(0x0012, destination_id=destination_id)

    def get_hardware_info(self, destination_id=None):
        """Query the device's hardware info and cache key fields.

        Sets :attr:`serial_number`, :attr:`model` and
        :attr:`number_of_channels` as a side effect.

        Args:
            destination_id: Key into :attr:`destination`.

        Returns:
            dict: Serial number, model, hardware/software versions, notes and
            channel count.
        """
        message_dict = self.query(0x0005, destination_id=destination_id)
        serialnum, model, hwtype, swversion, notes, hwversion, modstate, nchans = struct.unpack(
            '<I8sHI48s12xHHH', message_dict['data'])
        if serialnum != 0 and len(str(serialnum)) != 8:
            serialnum = int(hex(serialnum)[2:-1])

        hardware_dict = {
            'serial_number': serialnum,
            'model': str(model).replace('\x00', ''),
            'hardware_type': hwtype,
            'software_version': swversion,
            'notes': str(notes).replace('\x00', ''),
            'hardware_version': hwversion,
            'modstate': modstate,
            'number_of_channels': nchans}
        self.serial_number = serialnum

        try:
            self.model = self.serial_num_to_device_types[int(str(serialnum)[0:2])]
        except KeyError:
            self.model = ['Dummy', 'Serial number not recognised in the serial_num_to_device_types']
            self._logger.warn('Serial number not recognised. Model set to Dummy')
        self.number_of_channels = nchans
        return hardware_dict

    def get_status_update(self):
        """Request a status update. Must be overridden per device.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError

    def update_status(self, returned_message):
        """Update device properties from a status update message.

        Must be overridden per device, since the status format and commands
        vary between models.

        Args:
            returned_message: The decoded message from a status update request.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError

    def staying_alive(self, destination_id=None):
        """Send keep-alive messages so the controller knows the PC is up.

        Args:
            destination_id: Key(s) into :attr:`destination`; defaults to all
                destinations.
        """
        if destination_id is None:
            destination_id = list(self.destination.keys())
        else:
            if not hasattr(destination_id, '__iter__'):
                destination_id = tuple(destination_id)
        for dest in destination_id:
            self._logger.debug(str(dest))
            self.write(0x0492, destination_id=dest)
        self._logger.debug(str(destination_id) + str(dest))

    def _waitForReply(self):
        reply = ''
        t0 = time.time()
        while len(reply) == 0:
            try:
                reply = self.read()
            except struct.error:
                reply = ''
            time.sleep(0.1)
            if time.time() - t0 > self.timeout:
                return False, ''
        return True, reply


if __name__ == '__main__':
    # microscope_stage = APT_VCP(port = 'COM12',source = 0x01,destination = 0x21)

    dicc = detect_APT_VCP_devices()
    print('Here', dicc)
