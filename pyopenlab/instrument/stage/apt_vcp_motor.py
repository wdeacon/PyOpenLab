# -*- coding: utf-8 -*-
"""Thorlabs APT virtual-COM-port motor controllers (base classes and converters).

This module implements the Thorlabs APT serial protocol for stepper and DC-servo
motor controllers. Communication is built on :class:`APT_VCP`, which frames the
fixed 6-byte APT message header plus optional data packet; positions, velocities
and accelerations are exchanged as raw encoder counts and converted to/from real
units (mm, deg, mm/s, mm/s^2) by the per-controller ``convert`` method using the
stage-specific encoder-count calibration (``EncCnt``) and timer constants.
"""
import struct
import time
import types

import numpy as np
import serial

from pyopenlab.instrument.apt_virtual_com_port import APT_VCP
from pyopenlab.instrument.stage import Stage
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import DumbNotifiedProperty
from pyopenlab.utils.notified_property import NotifiedProperty
from pyopenlab.utils.notified_property import register_for_property_changes

DC_status_motors = {'BBD102/BBD103': [], 'TDC001': [], 'KDCT101': []}
DEBUG = False


class APT_parameter(NotifiedProperty):
    """A quick way of creating a property that alters an apt parameter.

    NB the property will be read immediately after it's written, to ensure
    that the value we send to any listening controls/indicators is correct
    (otherwise we'd send them the value that was requested, even if it was
    not valid).  This behaviour can be disabled by setting read_back to False
    in the constructor.
    """

    def __init__(self, parameter_name, doc=None, read_back=True):
        """Create a property that reads and writes the given APT parameter.

        This internally uses the ``get_APT_parameter`` and ``set_APT_parameter``
        methods, so make sure the owning class provides them.

        Args:
            parameter_name: Name of the APT parameter to read/write.
            doc: Docstring for the property; a default is generated if omitted.
            read_back: If True, re-read the parameter after writing so listeners
                receive the value the hardware actually accepted, not the
                requested value.
        """
        if doc is None:
            doc = "Adjust the APT parameter '{0}'".format(parameter_name)
        super(APT_parameter, self).__init__(fget=self.fget,
                                            fset=self.fset,
                                            doc=doc,
                                            read_back=read_back)
        self.parameter_name = parameter_name

    def fget(self, obj):
        return obj.get_APT_parameter(self.parameter_name)

    def fset(self, obj, value):
        obj.set_APT_parameter(self.parameter_name, value)


class APT_VCP_motor(APT_VCP, Stage):
    """Common APT virtual-COM-port communication for Thorlabs motor controllers.

    Subclasses supply the unit/count conversion (``convert``) and any
    controller-specific status decoding; this base class wires up the serial
    link, the per-axis destination map, the status bit masks and the standard
    APT parameter properties.

    Note:
        ``convert`` here is a no-op that prints a message and returns the value
        unchanged; subclasses (``DC_APT``, ``Stepper_APT_*``) must override it,
        otherwise positions/velocities are sent and read as raw encoder counts.
    """

    axis_names = ('x',)

    def __init__(self,
                 port=None,
                 source=0x01,
                 destination=None,
                 use_si_units=False,
                 stay_alive=False,
                 unit='m',
                 **kwargs):
        """Open the serial port and configure source/destination and status masks.

        Args:
            port: Serial port name (e.g. ``'COM12'`` or ``'/dev/ttyUSB0'``).
            source: APT source address byte for this host (default ``0x01``).
            destination: APT destination address(es). Either a single address
                (mapped to axis ``'x'``) or a dict mapping axis name to address;
                the dict keys become ``axis_names``.
            use_si_units: Passed through to :class:`APT_VCP`.
            stay_alive: If True, keep the controller's watchdog alive.
            unit: Stage unit string passed to :class:`Stage` (default ``'m'``).
            **kwargs: Ignored; accepted for subclass compatibility.
        """
        APT_VCP.__init__(self,
                         port=port,
                         source=source,
                         destination=destination,
                         use_si_units=use_si_units,
                         stay_alive=stay_alive)  # this opens the port
        Stage.__init__(self, unit=unit)
        if self.model[1] in DC_status_motors:
            # Set the bit mask for DC controllers
            self.status_bit_mask = np.array(
                [[0x00000001, 'forward hardware limit switch is active'],
                 [0x00000002, 'reverse hardware limit switch is active'],
                 [0x00000010, 'in motion, moving forward'],
                 [0x00000020, 'in motion, moving reverse'],
                 [0x00000040, 'in motion, jogging forward'],
                 [0x00000080, 'in motion, jogging reverse'], [0x00000200, 'in motion, homing'],
                 [0x00000400, 'homed (homing has been completed)'], [0x00001000, 'tracking'],
                 [0x00002000, 'settled'], [0x00004000, 'motion error (excessive position error)'],
                 [0x01000000, 'motor current limit reached'], [0x80000000, 'channel is enabled']])
            self.velocity_scaling_factor = 204.8  # for converting velocity to mm/sec
        else:
            # Set the bit mask for normal motor controllers
            self.status_bit_mask = np.array(
                [[0x00000001, 'forward (CW) hardware limit switch is active'],
                 [0x00000002, 'reverse (CCW) hardware limit switch is active'],
                 [0x00000004, 'forward (CW) software limit switch is active'],
                 [0x00000008, 'reverse (CCW) software limit switch is active'],
                 [0x00000010, 'in motion, moving forward (CW)'],
                 [0x00000020, 'in motion, moving reverse (CCW)'],
                 [0x00000040, 'in motion, jogging forward (CW)'],
                 [0x00000080, 'in motion, jogging reverse (CCW)'], [0x00000100, 'motor connected'],
                 [0x00000200, 'in motion, homing'],
                 [0x00000400, 'homed (homing has been completed)'],
                 [0x00001000, 'interlock state (1 = enabled)']])

            # delattr(self, 'get_qt_ui')
        if type(destination) != dict and len(self.destination) == 1:
            self.destination = {'x': destination}

        else:
            self.axis_names = tuple(destination.keys())
            self.destination = destination

        self.make_all_parameters()
        self._recusive_move_num = 0

    '''MOVEMENT'''

    #    def _waitForReply(self, msgCode, replysize):
    #        self.write(msgCode)
    #        reply = self.ser.read(replysize)
    #        t0 = time.time()
    #        while len(reply) == replysize:
    #            reply = self.ser.read(replysize)
    #            time.sleep(0.1)
    #            if time.time() - t0 > 30:
    #                return False
    #        return True

    def _waitFinishMove(self, axis=None, debug=False):
        """Block until the given axis (or all axes) report no 'in motion' status.

        Args:
            axis: Axis to wait on; if None, wait on every configured axis.
            debug: If truthy (or module-level ``DEBUG``), print each status poll.
        """
        if axis is None:
            destination_ids = list(self.destination.keys())
        else:
            destination_ids = [axis]
        for dest in destination_ids:
            status = self.get_status_update(axis=dest)
            if debug > 0 or DEBUG:
                print(status)

            while any(['in motion' in x[1] for x in status]):
                time.sleep(0.1)
                status = self.get_status_update(axis=dest)

    def home(self, axis=None):
        """Send the APT home command and block until homing completes.

        Args:
            axis: Axis to home; if None, home every axis in ``axis_names``.
        """
        if axis == None:
            destination_ids = self.axis_names
        else:
            destination_ids = tuple(axis)
        for dest in destination_ids:
            self.write(0x0443, destination_id=dest)
            #        self._waitForReply(0x0444, 6)
            self._waitFinishMove()

    def move(self, pos, axis=None, relative=False, channel_number=None, block=True):
        """Move one or more axes to absolute or relative positions.

        Positions are converted from real units to encoder counts via
        ``convert`` and packed into an APT ``MGMSG_MOT_MOVE_ABSOLUTE`` (0x0453)
        message. On a :class:`struct.error` the move is retried recursively up
        to 10 times before raising.

        Args:
            pos: Target position, or an iterable of positions (one per axis when
                ``axis`` is None and the length matches ``axis_names``).
            axis: Axis or iterable of axes to move; if None, infer from ``pos``.
            relative: If True, add ``pos`` to the current position of each axis.
            channel_number: APT channel number (defaults to 1).
            block: If True, wait for the move to finish before returning.

        Raises:
            Exception: If the move fails more than 10 times in a row.
        """
        if channel_number is None:
            channel_number = 1
        if not hasattr(pos, '__iter__'):
            pos = [pos]
        elif type(pos) == tuple:
            pos = list(pos)
        if axis is None:
            if len(pos) == len(self.axis_names):
                axes = self.axis_names
            else:
                self._logger.warn('What axis shall I move?')
        else:
            axes = tuple(axis)
        #create list of positions for each axis
        pos_list = [0] * len(self.axis_names)
        for i, axis in enumerate(axes):
            axis_number = np.where(np.array(self.axis_names) == [axis])[0][0]
            pos_list[axis_number] = pos[i]
        pos = pos_list
        for axis in axes:
            axis_number = np.where(np.array(self.axis_names) == [axis])[0][0]
            if relative:
                pos[axis_number] = self.position[axis_number] + pos[axis_number]

            pos_in_counts = int(
                np.round(self.convert(pos[axis_number], 'position', 'counts'), decimals=0))
            data = bytearray(
                struct.pack('<HL', self.channel_number_to_identity[channel_number], pos_in_counts))
            try:
                self.write(0x0453, data=data, destination_id=axis)
                if block == True:
                    self._waitFinishMove()
            except struct.error as e:
                self.log('Move failed with ' + str(e), 'warning')
                self._recusive_move_num += 1
                if self._recusive_move_num > 10:
                    self._recusive_move_num = 0
                    raise Exception('Stage move failed!')
                self.move(pos[axis_number], axis=axis, channel_number=channel_number, block=block)
            self._recusive_move_num = 0
            axis_number += 1

    '''PARAMETERS'''

    def get_status_update(self, channel_number=1, axis=None):
        """Query the controller status (0x0490 for DC, 0x0480 otherwise).

        Args:
            channel_number: APT channel number (defaults to 1).
            axis: Destination axis to query.

        Returns:
            The decoded status rows from :meth:`update_status`.
        """
        if self.model[1] in DC_status_motors:
            returned_message = self.query(0x0490,
                                          param1=self.channel_number_to_identity[channel_number],
                                          destination_id=axis)
        else:
            returned_message = self.query(0x0480,
                                          param1=self.channel_number_to_identity[channel_number],
                                          destination_id=axis)
        return self.update_status(returned_message['data'])

    def update_status(self, returned_message, debug=False):
        """Decode an APT status-update data packet into active status flags.

        The packet layout differs between DC controllers and stepper/motor
        controllers, so the struct format is chosen from ``model``. The status
        bits are matched against ``status_bit_mask`` and the matching rows are
        stored on ``self.status`` and returned.

        Args:
            returned_message: Raw ``data`` bytes from a status-update reply.
            debug: If truthy (or module-level ``DEBUG``), print packet length
                and decoded status.

        Returns:
            numpy.ndarray: The ``[mask, description]`` rows whose bit is set.
        """
        if debug > 0 or DEBUG == True:
            N = len(returned_message)
            print("returned_message length:", N)
        if self.model[1] in DC_status_motors:
            channel, position, velocity, Reserved, status_bits = struct.unpack(
                r'<HLHHI', returned_message)
            #HLHHI
            #H - 2, L - 4, I - 4
            # self.position = position
            # self.velocity = velocity / self.velocity_scaling_factor
        else:

            channel, position, EncCnt, status_bits, ChanIdent2, _, _, _ = struct.unpack(
                r'<HILIHLLL', returned_message)
            # print "Status bits",status_bits
            # print "self.status_bit_mask",self.status_bit_mask[:, 0]
        bitmask = self._bit_mask_array(status_bits, [int(i) for i in self.status_bit_mask[:, 0]])
        self.status = self.status_bit_mask[np.where(bitmask)]
        if debug > 0 or DEBUG == True:
            print(self.status)
        return self.status

    def init_no_flash_programming(self):
        """ This message must be sent on startup to tell the controller
        the source and destination address - The manual says this MUST be
        sent as part of the intialisation process

        Labled as: MGMSG_HW_NO_FLASH_PROGRAMMING
        """
        self.write(0x0018)

    def get_position(self, axis=None, channel_number=1):
        """Read the live position from the controller, converted to real units.

        Args:
            axis: Axis to read; if None, return an array of positions for every
                axis in ``axis_names``.
            channel_number: APT channel number (defaults to 1).

        Returns:
            The position in real units (via ``convert``), or a numpy array of
            positions when ``axis`` is None.

        Raises:
            ValueError: If ``axis`` is not one of ``axis_names``.
        """
        if axis is None:
            return np.array(([self.get_position(axis) for axis in self.axis_names]))
        else:
            if axis not in self.axis_names:
                raise ValueError("{0} is not a valid axis, must be one of {1}".format(
                    axis, self.axis_names))

            returned_message = self.query(0x0411,
                                          param1=self.channel_number_to_identity[channel_number],
                                          destination_id=axis)
            data = returned_message['data']
            channel_id, position = struct.unpack(r'<HL', data)
            # position = self.convert_to_SI_position(position)
            return self.convert(position, 'counts', 'position')

    def set_position(self, position, channel_number=1, axis=None):
        """Overwrite the controller's live position counter (0x0410).

        This sets the controller's internal count without moving the motor and
        is rarely needed; prefer homing to establish a reference. The value is
        sent verbatim as counts (no unit conversion).

        Args:
            position: New position counter value, in encoder counts.
            channel_number: APT channel number (defaults to 1).
            axis: Destination axis.
        """
        data = bytearray(
            struct.pack('<HL', self.channel_number_to_identity[channel_number], position))
        self.write(0x0410, data=data, destination_id=axis)

    position = property(get_position, set_position)

    def convert(self, value, from_, to_):
        """Convert between counts and real units; base implementation is a no-op.

        Subclasses override this to apply the stage calibration. Here it simply
        prints and returns ``value`` unchanged.

        Args:
            value: Value to convert.
            from_: Source unit name (e.g. ``'counts'``).
            to_: Target unit name (e.g. ``'position'``).

        Returns:
            ``value`` unchanged.
        """
        print('Not doing anything from ', from_, ' to ', to_)
        return value

    def make_parameter(self, param_dict, destination_id=None):
        """Create a getter, setter and property for one APT parameter.

        Most APT parameters share the same get/set command structure, so this
        wraps their creation. It attaches ``get_<name>`` and ``set_<name>``
        methods plus a ``<name>`` property to the instance. Entries in
        ``param_names`` that are plain strings are passed through; entries that
        are ``[name, unit]`` lists are converted via ``convert`` on read/write.

        Examples:
            Create ``velocity_params`` together with ``get_velocity_params`` and
            ``set_velocity_params``; the dict has ``channel_num``,
            ``min_velocity``, ``acceleration`` and ``max_velocity``::

                self.make_parameter(dict(
                    name='velocity_params', set=0x0413, get=0x0414,
                    structure='HLLL',
                    param_names=['channel_num', ['min_velocity', 'velocity'],
                                 ['acceleration', 'acceleration'],
                                 ['max_velocity', 'velocity']]))

        Args:
            param_dict: Mapping with keys ``name`` (property name), ``set`` and
                ``get`` (APT command codes), ``structure`` (struct format of the
                data packet) and ``param_names`` (names of the packed fields).
            destination_id: APT destination axis the get/set messages target.
        """

        def getter(selfie, channel_number=1):
            returned_message = selfie.query(
                param_dict['get'],
                param1=selfie.channel_number_to_identity[channel_number],
                destination_id=destination_id)
            data = returned_message['data']
            data = struct.unpack('<' + param_dict['structure'], data)
            params = {}
            index = 0
            for name in param_dict['param_names']:
                if type(name) == str:
                    params[name] = data[index]
                elif type(name) == list:
                    params[name[0]] = selfie.convert(data[index], 'counts', name[1])
                index += 1
            return params

        def setter(selfie, params, channel_number=None):
            if channel_number is None:
                channel_number = params['channel_num']
            unstructured_data = [
                '<' + param_dict['structure'], selfie.channel_number_to_identity[channel_number]]
            for name in param_dict['param_names']:
                if name != 'channel_num':
                    if type(name) == str:
                        unstructured_data += [params[name]]
                    elif type(name) == list:
                        unstructured_data += [selfie.convert(params[name[0]], name[1], 'counts')]
            data = struct.pack(*unstructured_data)
            selfie.write(param_dict['set'], data=data, destination_id=destination_id)

        setattr(self, 'get_' + param_dict['name'], types.MethodType(getter, self))
        setattr(self, 'set_' + param_dict['name'], types.MethodType(setter, self))
        try:
            setattr(self, param_dict['name'],
                    property('get_' + param_dict['name'], 'set_' + param_dict['name']))
        except AttributeError:
            print(param_dict['name'], ' already exists')

    def make_all_parameters(self):
        """Create the standard APT parameter properties for every axis.

        Note:
            ``make_parameter`` builds the read/write property with
            ``property('get_<name>', 'set_<name>')``, passing strings rather
            than the bound methods. ``property`` then has a string as ``fget``,
            so accessing the property attribute (rather than the explicit
            ``get_<name>``/``set_<name>`` methods) does not actually call the
            getter/setter. This is a behavioural bug and is left as-is; use the
            generated ``get_<name>``/``set_<name>`` methods directly.
        """
        for axis in self.destination:
            self.make_parameter(dict(name=axis + '_encoder_counts',
                                     set=0x0409,
                                     get=0x040A,
                                     structure='HL',
                                     param_names=['channel_num', 'encoder_counts']),
                                destination_id=axis)
            # self.make_parameter(dict(name='position', set=0x0410, get=0x0411, structure='HL', param_names=['channel_num', ['position', 'distance']]))
            self.make_parameter(dict(name=axis + '_velocity_params',
                                     set=0x0413,
                                     get=0x0414,
                                     structure='HLLL',
                                     param_names=[
                                         'channel_num', ['min_velocity', 'velocity'],
                                         ['acceleration', 'acceleration'],
                                         ['max_velocity', 'velocity']]),
                                destination_id=axis)
            self.make_parameter(dict(name=axis + '_jog_params',
                                     set=0x0416,
                                     get=0x0417,
                                     structure='HHLLLLH',
                                     param_names=[
                                         'channel_num', ['jog_step_size', 'distance'],
                                         ['jog_min_velocity', 'velocity'],
                                         ['jog_acceleration', 'acceleration'],
                                         ['jog_max_velocity', 'velocity'], 'jog_stop_mode']),
                                destination_id=axis)
            self.make_parameter(dict(name=axis + '_gen_move_params',
                                     set=0x043C,
                                     get=0x043B,
                                     structure='HL',
                                     param_names=['channel_num', 'backlash']),
                                destination_id=axis)
            self.make_parameter(dict(name=axis + '_power_params',
                                     set=0x0426,
                                     get=0x0427,
                                     structure='HHH',
                                     param_names=['channel_num', 'RestPower', 'MovePower']),
                                destination_id=axis)
            self.make_parameter(dict(name=axis + '_move_rel_params',
                                     set=0x0446,
                                     get=0x0447,
                                     structure='HL',
                                     param_names=['channel_num', 'rel_dist']),
                                destination_id=axis)
            self.make_parameter(dict(name=axis + '_move_abs_params',
                                     set=0x0451,
                                     get=0x0452,
                                     structure='HL',
                                     param_names=['channel_num', 'abs_dist']),
                                destination_id=axis)
            self.make_parameter(dict(name=axis + '_home_params',
                                     set=0x0441,
                                     get=0x0442,
                                     structure='HHHLL',
                                     param_names=[
                                         'channel_num', 'direction', 'limit_switch', 'velocity',
                                         'offset']),
                                destination_id=axis)
        # self.make_parameter(dict(name=, set=, get=, structure=, param_names=['channel_num']))


class DC_APT(APT_VCP_motor):
    """APT DC-servo controller with per-stage count/unit conversion.

    Conversion relies on the encoder-count calibration ``EncCnt`` (counts/mm,
    selected by ``stage_type``) and the controller timer constant ``t_constant``;
    if either is unset, ``convert`` returns the raw value and logs a warning.
    """

    #The different EncCnt (calibrations) for the different stage types
    DC_stages_EncCnt = {
        'MTS': 34304.0,
        'PRM': 1919.64 * 1E3,
        'Z8': 34304.0,
        'Z6': 24600,
        'DDSM100': 2000,
        'DDS': 20000,
        'MLS': 20000}

    def __init__(self,
                 port=None,
                 source=0x01,
                 destination=None,
                 use_si_units=True,
                 unit='m',
                 stay_alive=True,
                 stage_type=None):
        """Open the controller and set the timer constant and encoder calibration.

        Args:
            port: Serial port name.
            source: APT source address (default ``0x01``).
            destination: APT destination address or axis->address dict.
            use_si_units: Ignored; always forwarded as True to the base class.
            unit: Stage unit string (default ``'m'``).
            stay_alive: Keep the controller watchdog alive (default True).
            stage_type: Key into ``DC_stages_EncCnt`` selecting the encoder
                calibration; unknown/None leaves ``EncCnt`` as None.
        """
        APT_VCP_motor.__init__(self,
                               port=port,
                               source=source,
                               destination=destination,
                               use_si_units=True,
                               unit=unit,
                               stay_alive=stay_alive)  # this opens the port
        #Setup up conversion factors
        if self.model[
                1] == 'BBD102/BBD103':  #Once the TBD001 controller is added it needs to be added here
            self.t_constant = 102.4E-6
        elif self.model[1] in ['TDC001', 'KDCT101']:
            self.t_constant = 2048.0 / (6.0E6)
        else:
            self.t_constant = None

        if stage_type != None:
            try:
                self.EncCnt = float(self.DC_stages_EncCnt[stage_type])
            except KeyError:
                self.EncCnt = None
                self._logger.warn(
                    'The stage type suggested is not listed and therefore a calibration cannot be set'
                )
        else:
            self.EncCnt = None

    def convert(self, value, from_, to_):
        if None in (self.EncCnt, self.t_constant):
            self._logger.warn(
                'Conversion impossible: one of the constants has not been implemented')
            return value
        if from_ == 'counts':
            return self.counts_to[to_](self, value)
        elif to_ == 'counts':
            return self.si_to[from_](self, value)
        else:
            self._logger.warn(
                ('Converting %s to %s is not possible!, returning raw value' % (from_, to_)))
            return value

    def counts_to_pos(self, counts):
        return (counts / self.EncCnt) * 1E3

    def pos_to_counts(self, pos):
        return (pos * self.EncCnt / 1E3)

    def counts_to_vel(self, counts):
        return (counts / (self.EncCnt * self.t_constant * 65536)) * 1E3

    def vel_to_counts(self, vel):
        return (vel * 65536 * self.t_constant * self.EncCnt / 1E3)

    def counts_to_acc(self, counts):
        return (counts / (self.EncCnt * self.t_constant**2 * 65536)) * 1E3

    def acc_to_counts(self, acc):
        return (self.EncCnt * self.t_constant**2 * 65536 * acc / 1E3)

    def move_step(self, axis, direction):
        self.move_rel(self.stepsize * direction, axis)

    def _waitFinishMove(self, axis=None, debug=False):
        """A simple function to force movement to block the console """
        if axis == None:
            destination_ids = list(self.destination.keys())
        else:
            destination_ids = [axis]
        for dest in destination_ids:
            status = self.get_status_update(
                axis=dest)  # \ # and all([not x[1].endswith('homing') for x in status])\
            while any(['in motion' in x[1] for x in status]):

                time.sleep(0.1)
                status = self.get_status_update(axis=dest)
                if debug > 0 or DEBUG:
                    print(status)

    def home(self, axis=None):
        """Rehome the stage with an axis input """
        if axis == None:
            destination_ids = self.axis_names
        else:
            destination_ids = tuple(axis)
        for dest in destination_ids:
            self.write(0x0443, destination_id=dest)
            self._waitForReply()
            self._waitFinishMove()

    counts_to = {
        'position': counts_to_pos,
        'velocity': counts_to_vel,
        'acceleration': counts_to_acc}
    si_to = {'position': pos_to_counts, 'velocity': vel_to_counts, 'acceleration': acc_to_counts}


class Stepper_APT_std(APT_VCP_motor):
    """Standard (non-Trinamics) APT stepper controller.

    Uses a single counts/mm calibration (``EncCnt``, microsteps/mm selected by
    ``stage_type``) for position conversion; velocity/acceleration are not
    separately converted.
    """

    #The different EncCnt (calibrations) for the different stage types is microstep/mm
    stepper_stages_EncCnt = {
        'DRV001': 51200,
        'DRV013': 25600,
        'DRV014': 25600,
        'NRT': 25600,
        'LTS': 25600,
        'DRV': 20480,
        'FW': 71,
        'NR': 4693,}

    def __init__(self,
                 port=None,
                 source=0x01,
                 destination=None,
                 use_si_units=True,
                 stay_alive=True,
                 stage_type=None):
        """Open the controller and set the encoder calibration for a stepper stage.

        Args:
            port: Serial port name.
            source: APT source address (default ``0x01``).
            destination: APT destination address or axis->address dict.
            use_si_units: Ignored; always forwarded as True to the base class.
            stay_alive: Keep the controller watchdog alive (default True).
            stage_type: Key into ``stepper_stages_EncCnt`` selecting the
                microstep/mm calibration; unknown/None leaves ``EncCnt`` None.
        """
        APT_VCP_motor.__init__(self,
                               port=port,
                               source=source,
                               destination=destination,
                               use_si_units=True,
                               stay_alive=stay_alive)  # this opens the port
        #Setup up conversion factors

        if stage_type != None:
            try:
                self.EncCnt = float(self.stepper_stages_EncCnt[stage_type])
            except KeyError:
                self.EncCnt = None
                self._logger.warn(
                    'The stage type suggested is not listed and therefore a calibration cannot be set'
                )
        else:
            self.EncCnt = None

    def convert(self, value, from_, to_):
        if self.EncCnt == None:
            self._logger.warn(
                'Conversion impossible: one of the constants has not been implemented')
            return value
        if from_ == 'counts':
            return self.counts_to_si(value)
        elif to_ == 'counts':
            return self.si_to_counts(value)
        else:
            self._logger.warn(
                ('Converting %s to %s is not possible!, returning raw value' % (from_, to_)))
            return value

    def counts_to_si(self, counts):
        return (counts / self.EncCnt) * 1E3

    def si_to_counts(self, pos):
        return (pos * self.EncCnt / 1E3)


class Stepper_APT_trinamics(APT_VCP_motor):
    """APT stepper controller using the Trinamics-based count calibrations.

    Note:
        ``convert`` tests ``self.t_constant``, but this class never assigns
        ``t_constant`` (unlike ``DC_APT``), so the first call raises
        ``AttributeError``. The velocity/acceleration converters instead bake in
        the fixed factors 53.68 and 90.9. This is a runtime bug and is left
        as-is; set ``t_constant`` on the instance before converting.
    """

    #The different EncCnt (calibrations) for the different stage types is microstep/mm
    stepper_stages_EncCnt = {
        'DRV001': 819200,
        'DRV013': 409600,
        'DRV014': 409600,
        'NRT': 409600,
        'LTS': 409600,
        'MLJ': 409600,
        'DRV': 327680,
        'FW': 1138,
        'NR': 75091,}

    def __init__(self,
                 port=None,
                 source=0x01,
                 destination=None,
                 use_si_units=True,
                 stay_alive=True,
                 stage_type=None):
        """Open the controller and set the encoder calibration for a Trinamics stage.

        Args:
            port: Serial port name.
            source: APT source address (default ``0x01``).
            destination: APT destination address or axis->address dict.
            use_si_units: Ignored; always forwarded as True to the base class.
            stay_alive: Keep the controller watchdog alive (default True).
            stage_type: Key into ``stepper_stages_EncCnt`` selecting the
                microstep/mm calibration; unknown/None leaves ``EncCnt`` None.
        """
        APT_VCP_motor.__init__(self,
                               port=port,
                               source=source,
                               destination=destination,
                               use_si_units=True,
                               stay_alive=stay_alive)  # this opens the port
        #Setup up conversion factors
        if stage_type != None:
            try:
                self.EncCnt = float(self.stepper_stages_EncCnt[stage_type])
            except KeyError:
                self.EncCnt = None
                self._logger.warn(
                    'The stage type suggested is not listed and therefore a calibration cannot be set'
                )
        else:
            self.EncCnt = None

    def convert(self, value, from_, to_):
        if None in (self.EncCnt, self.t_constant):
            self._logger.warn(
                'Conversion impossible: one of the constants has not been implemented')
            return value
        if from_ == 'counts':
            return self.counts_to[to_](self, value)
        elif to_ == 'counts':
            return self.si_to[from_](self, value)
        else:
            self._logger.warn(
                ('Converting %s to %s is not possible!, returning raw value' % (from_, to_)))
            return value

    def counts_to_pos(self, counts):
        return (counts / self.EncCnt) * 1E3

    def pos_to_counts(self, pos):
        return (pos * self.EncCnt / 1E3)

    def counts_to_vel(self, counts):
        return (counts / (self.EncCnt * 53.68)) * 1E3

    def vel_to_counts(self, vel):
        return (vel * 53.68 * self.EncCnt / 1E3)

    def counts_to_acc(self, counts):
        return (counts / (self.EncCnt / 90.9)) * 1E3

    def acc_to_counts(self, acc):
        return (self.EncCnt / 90.9 * acc / 1E3)

    counts_to = {
        'position': counts_to_pos,
        'velocity': counts_to_vel,
        'acceleration': counts_to_acc}
    si_to = {'position': pos_to_counts, 'velocity': vel_to_counts, 'acceleration': acc_to_counts}


class MFF102(APT_VCP_motor):
    """Thorlabs MFF10x motorised filter flipper (two discrete positions).

    Position is a boolean (0/1) flipper state read from the status bits and set
    by jogging; ``move``/``convert`` from the base class are not used here.
    """

    def jog_forward(self):  # 1 -> 0 (blame thorlabs)
        self._write(0x046A, param2=0x01)
        self._waitFinishMove()

    def jog_backward(self):  # 0 -> 1
        self._write(0x046A, param2=0x02)
        self._waitFinishMove()

    def get_status_bits(self):
        data = self.query(0x0429, blocking=True)['data']
        status_bits = struct.unpack(r'3h', data)
        return status_bits

    def get_position(self):
        return self.get_status_bits()[1] - 1

    def set_position(self, val):
        if (pos := self.position) > val:
            self.jog_forward()
        elif pos < val:
            self.jog_backward()

    position = NotifiedProperty(get_position, set_position)

    def toggle(self):
        self.position = not self.position

    def home(self):
        self.set_position(0)

    def _waitFinishMove(self):
        pass

    def get_qt_ui(self):
        return FlipperUI(self)


class FlipperUI(QuickControlBox):
    """Minimal control box exposing the flipper position as a checkbox."""

    def __init__(self, instr):
        super().__init__()
        self.instr = instr
        self.add_checkbox('position')
        self.auto_connect_by_name(controlled_object=instr)

    # getstatusbits = 0x0429


if __name__ == '__main__':
    print("pass")
    # microscope_stage = APT_VCP_motor(port='COM12', source=0x01, destination=0x21)
    r = DC_APT(port='COM1', destination=0x01, stage_type='MLS')
    DEBUG = True
    f = MFF102(
        'COM17',
        destination=0x01,
    )
    f.show_gui(False)
    # tdc_cube = Stepper_APT_trinamics(port='/dev/ttyUSB1', source=0x01, destination=0x50)
    # # tdc_cube2 = APT_VCP_motor(port='COM20', source=0x01, destination=0x50)

    # tdc_cube.show_gui()
    # print tdc_cube.position
    # tdc_cube.home()
    # delattr(tdc_cube, 'get_qt_ui')
    # print tdc_cube.channel_number_to_identity['1']
    # tdc_cube.get_status_update()
    # print 'Status: ', tdc_cube.status
    # print 'Position: ', tdc_cube.get_position()

    # tdc_cube.make_all_parameters()
    # print tdc_cube.get_velocity_params()
    # print tdc_cube.velocity_params
    # tdc_cube.show_gui()
    # print tdc_cube.get_gen_move_params()
    # print tdc_cube.get_haha()

    # tdc_cube.home()

    # tdc_cube.move(0)
    # time.sleep(10)
