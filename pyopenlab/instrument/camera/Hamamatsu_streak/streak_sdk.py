# -*- coding: utf-8 -*-
"""TCP/IP (RemoteEx) wrapper for Hamamatsu streak cameras.

Implements :class:`StreakSdk`, a VISA-backed driver speaking the RemoteEx protocol
documented in the RemoteEx Programmers Handbook, plus the streak error codes.
"""

import os
import pprint
import re
import socket
import struct
import time

import numpy as np
import pyvisa as visa

from pyopenlab.instrument.visa_instrument import VisaInstrument

PrettyPrinter = pprint.PrettyPrinter(indent=4)

TIMEOUT = 5000  # in milliseconds
BUFFER_SIZE = 4096
SLEEPING_TIME = 0.1


class StreakError(Exception):
    """Exception raised for non-success RemoteEx error codes.

    Attributes:
        error_code (int): The numeric RemoteEx error code.
        error_name (str): The human-readable description of the code.
        msg: The command/context that produced the error.
        reply: The full reply text from the camera.
    """

    def __init__(self, code, msg, reply):
        if isinstance(code, str):
            code = int(code)
        super(StreakError, self).__init__()
        self.msg = msg
        self.reply = reply
        self.error_code = code
        self.error_name = ERROR_CODES[code]

    def __str__(self):
        return '%s Sent: %s Reply: %s' % (self.error_name, self.msg, self.reply)


class StreakSdk(VisaInstrument):
    """
    Implements the RemoteExProgrammersHandbook91

    Not Implemented Functions:
        'MainParamInfo', 'MainParamInfoEx', 'GenParamInfo', 'GenParamInfoEx', 'AcqLiveMonitor', 'AcqLiveMonitorTSInfo',
        'acqLiveMonitorTSFormat', 'CamSetupSendSerial', 'ImgStatusSet', 'ImgRingBufferGet', 'ImgAnalyze', 'ImgRoiGet',
        'ImgRoiSet', 'ImgRoiSelectedRoiGet', 'ImgRoiSelectedRoiSet', 'SeqCopyToSeparateImg', 'SeqImgIndexGet', '
        All of the auxiliary devices, processing, defect pixel tools
    """

    def __init__(self, address, start_app=False, get_all_parameters=False, **kwargs):
        """Open the command and data sockets to the RemoteEx server.

        Args:
            address (tuple): The streak TCP address as ``(TCP_IP, TCP_PORT)``; the data
                socket uses ``TCP_PORT + 1``.
            start_app (bool): If ``True``, start the HPDTA GUI on connect.
            get_all_parameters (bool): If ``True``, query every parameter on startup.
            **kwargs: Forwarded to the VISA instrument. ``CloseAppWhenDone`` closes the
                streak GUI when this instance is deleted.
        """
        visa_address = 'TCPIP::%s::%d::SOCKET' % address
        settings = dict(read_termination='\r',
                        write_termination='\r',
                        timeout=TIMEOUT,
                        query_delay=SLEEPING_TIME)
        super(StreakSdk, self).__init__(visa_address, settings)

        message = self.read()  # reads the default message that gets sent from RemoteEx
        if message != 'RemoteEx Ready':
            self._logger.warn('Not ready: %s' % message)

        self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_socket.connect((address[0], address[1] + 1))
        self.data_socket.settimeout(10)
        message = self.data_socket.recv(100).decode().rstrip()
        if message != 'RemoteEx Data Ready':
            self._logger.warn('Data socket not ready: %s' % message)
        self.clear_read_buffer()

        self.close_app_when_done = False
        if "CloseAppWhenDone" in kwargs:
            self.close_app_when_done = kwargs['CloseAppWhenDone']

        # Starting the HPDTA GUI
        if start_app:
            self.start_app()

        self._setup_parameter_dictionaries()

        # Getting all the parameters
        if get_all_parameters:
            self.get_parameter()

    def __del__(self):
        if self.close_app_when_done:
            self.send_command('AppEnd')
        super(StreakSdk, self).__del__()

    def reopen_connection(self):
        """Tear down and re-establish the command and data sockets.

        Useful when the remote app crashes, so the connection can be restarted without
        restarting the local Python process.
        """
        if hasattr(self, 'instr'):
            del self.instr
        if hasattr(self, 'data_socket'):
            self.data_socket.close()
            del self.data_socket

        settings = dict(read_termination='\r',
                        write_termination='\r',
                        timeout=TIMEOUT,
                        query_delay=SLEEPING_TIME)

        rm = visa.ResourceManager()
        self.instr = rm.open_resource(self._address, **settings)

        message = self.read()  # reads the default message that gets sent from RemoteEx
        if message != 'RemoteEx Ready':
            self._logger.warn('Not ready: %s' % message)

        address = self._address.split('::')[1:3]
        self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_socket.connect((address[0], int(address[1]) + 1))
        self.data_socket.settimeout(10)
        message = self.data_socket.recv(100).decode().rstrip()
        if message != 'RemoteEx Data Ready':
            self._logger.warn('Data socket not ready: %s' % message)
        self.clear_read_buffer()

    def query(self, msg, *args, **kwargs):
        """Send a query, logging it and validating the handshake reply.

        Args:
            msg (str): The command string to send.
            *args: Positional arguments forwarded to the underlying query.
            **kwargs: Keyword arguments forwarded to the underlying query.

        Returns:
            The reply portion of the handshaked response.
        """
        self._logger.debug("write: %s" % msg)
        full_reply = super(StreakSdk, self).query(msg, *args, **kwargs)
        self._logger.debug("read: %s" % full_reply)
        reply = self._handshake(msg, full_reply, *args, **kwargs)
        return reply

    def _handshake(self, message, full_reply, *args, **kwargs):
        """Validate that a command executed without errors.

        The streak replies with an error code (see ``ERROR_CODES``) and the command name.
        Status-only replies (codes 4/5) are skipped by reading and handshaking again.

        Args:
            message (str): The original command sent.
            full_reply (str): The raw reply received.
            *args: Forwarded to :meth:`read` when re-handshaking.
            **kwargs: Forwarded to :meth:`read` when re-handshaking.

        Returns:
            The reply payload on success, or ``None`` if the handshake failed (logged).

        Raises:
            StreakError: If the reply carries a genuine error code (handled internally and
                logged, not propagated).
        """
        try:
            split_reply = full_reply.split(',', 2)

            # Some commands have a response (len = 3), others simply have a handshake (len = 2)
            if len(split_reply) == 2:
                split_reply += ('',)
            error_code, command, reply = split_reply

            if error_code in ['4', '5']:
                # Some messages in the buffer simply state the streak status
                self._logger.debug('Useless reply:\t%s\t%s\t%s' % (error_code, command, reply))
                # They are generally not useful, so we handshake again
                full_reply = self.read(*args, **kwargs)
                return self._handshake(message, full_reply, *args, **kwargs)
            elif message.split('(')[0] != command:
                self._logger.error('Comparing this: %s \t to this: %s' %
                                   (message.split('(')[0], command))
                raise RuntimeError('Replied command does not match')
            elif error_code == '0':
                self._logger.debug('Handshake worked\t%s\t%s' % (command, reply))
                return reply
            else:
                raise StreakError(error_code, message, full_reply)
        except Exception as e:
            self._logger.warn('Handshake failed: %s' % e)

    def send_command(self, operation, *parameters, **kwargs):
        """Format a command and parameters into the RemoteEx string and send it.

        The command structure is ``operation(parameter1, parameter2, ...)``.

        Args:
            operation (str): The RemoteEx operation name.
            *parameters: Parameters to pass to the operation.
            **kwargs: Forwarded to :meth:`query`.

        Returns:
            The reply from :meth:`query`.
        """
        self._logger.debug("send_command: %s, %s, %s" % (operation, parameters, kwargs))
        msg = '%s(%s)' % (operation, ','.join(map(str, parameters)))
        return self.query(msg, **kwargs)

    def _setup_parameter_dictionaries(self):
        """Build ``self.parameters``, describing how to get/set every streak parameter.

        Streak parameters are hierarchical: some have a single level (e.g. Application),
        others two (e.g. Camera has Binning under Setup, Exposure under Live/Acquire/AI/PC).
        Each entry stores its get/set/info command names and a value tree.

        Note:
            TODO (pre-existing): turn parameters into CameraParameters for metadata bundling
            (blocked by names containing spaces/dots/slashes), and handle unavailable
            parameters and devices.
        """
        self.parameters = dict()

        # APPLICATION
        app_params = ['Date', 'Version', 'Directory', 'Title', 'Titlelong', 'ProgDataDir', 'type']
        self.parameters['Application'] = {
            'get': 'AppInfo',
            'set': None,
            'info': None,
            'value': {
                key: None for key in app_params}}

        # MAIN
        main_params = [
            'ImageSize', 'Message', 'Temperature', 'GateMode', 'MCPGain', 'Mode', 'Plugin',
            'Shutter', 'StreakCamera', 'TimeRange']
        self.parameters['Main'] = {
            'get': 'MainParamGet',
            'set': None,
            'info': 'MainParamInfo',
            'value': {
                key: None for key in main_params}}

        # GENERAL
        gen_params = [
            'RestoreWindowPos', 'UserFunctions', 'ShowStreakControl', 'ShowDelay1Control',
            'ShowDelay2Control', 'ShowSpectrControl']
        self.parameters['General'] = {
            'get': 'GenParamGet',
            'set': 'GenParamSet',
            'info': 'GenParamInfo',
            'value': {
                key: None for key in gen_params}}

        # ACQUISITION
        acquisition_params = [
            'DisplayInterval', '32BitInAI', 'WriteDPCFile', 'AdditionalTimeout',
            'DeactivateGrbNotInUse', 'CCDGainForPC', '32BitInPC', 'MoireeReduction']
        self.parameters['Acquisition'] = {
            'get': 'AcqParamGet',
            'set': 'AcqParamSet',
            'info': 'AcqParamInfoEx',
            'value': {
                key: None for key in acquisition_params}}

        # CAMERA
        setup_param = [
            'TimingMode', 'TriggerMode', 'TriggerSource', 'TriggerPolarity', 'ScanMode', 'Binning',
            'CCDArea', 'LightMode', 'Hoffs', 'HWidth', 'VOffs', 'VWidth', 'ShowGainOffset',
            'NoLines', 'LinesPerImage', 'ScrollingLiveDisplay', 'FrameTrigger', 'VerticalBinning',
            'TapNo', 'ShutterAction', 'Cooler', 'TargetTemperature', 'ContrastEnhancement',
            'Offset', 'Gain', 'XDirection', 'ScanSpeed', 'MechanicalShutter', 'Subtype',
            'AutoDetect', 'Wait2ndFrame', 'DX', 'DY', 'XOffset', 'YOffset', 'BPP', 'CameraName',
            'ExposureTime', 'ReadoutTime', 'OnChipAmp', 'CoolingFan', 'Cooler', 'ExtOutputPolarity',
            'ExtOutputDelay', 'ExtOutputWidth', 'LowLightSensitivity', 'AutomaticBundleHeight',
            'CameraInfo']
        # Two parameters called Offset and Width were not included (name shadowing, must be a bug in the program or a
        # typo in the manual). Additionally, all the sensor specific parameters were not included
        tab_param = [
            'Exposure', 'Gain', 'Offset', 'NrTrigger', 'Threshold', 'Threshold2', 'DoRTBackSub',
            'DoRTShading', 'NrExposures', 'ClearFrameBuffer', 'AmpGain', 'SMD', 'RecurNumber',
            'HVoltage', 'AMD', 'ASH', 'ATP', 'SOP', 'SPX', 'MCP', 'TDY', 'IntegrAfterTrig',
            'SensitivityValue', 'EMG', 'BGSub', 'RecurFilter', 'HightVoltage', 'StreakTrigger',
            'FGTrigger', 'SensitivitySwitch', 'BGOffset', 'ATN', 'SMDExtended', 'LightMode',
            'ScanSpeed', 'BGDataMemory', 'SHDataMemory', 'SensitivityMode', 'Sensitivity',
            'Sensitivity2Mode', 'Sensitivity2', 'ContrastControl', 'ContrastGain', 'ContrastOffset',
            'PhotonImagingMode', 'HighDynamicRangeMode', 'RecurNumber2', 'RecurFilter2',
            'FrameAvgNumber', 'FrameAvg']
        cam_params = dict(Setup={key: None for key in setup_param},
                          Live={key: None for key in tab_param},
                          Acquire={key: None for key in tab_param},
                          AI={key: None for key in tab_param},
                          PC={key: None for key in tab_param})
        self.parameters['Camera'] = {
            'get': 'CamParamGet',
            'set': 'CamParamSet',
            'info': 'CamParamInfoEx',
            'value': cam_params}

        # CORRECTIONS
        bkg_param = [
            'BackgroundSource', 'BackFilesForAcqModes', 'GeneralFile', 'LiveFile', 'AcquireFile',
            'AIFile', 'Constant', 'ClipZero', 'AutoBacksub']
        curv_param = ['CorrectionFile', 'AutoCurvature']
        defect_pixel_param = ['DefectCorrection', 'DefectPixelFile']
        shading_param = [
            'ShadingFile', 'ShadingConstant', 'AutoShading', 'SensitivityCorrection', 'LampFile']
        correction_params = dict(Background={key: None for key in bkg_param},
                                 Shading={key: None for key in curv_param},
                                 Curvature={key: None for key in defect_pixel_param},
                                 DefectPixel={key: None for key in shading_param})
        self.parameters['Corrections'] = {
            'get': 'CorParamGet',
            'set': 'CorParamSet',
            'info': 'CorParamInfoEx',
            'value': correction_params}

        # IMAGES
        img_params = [
            'AcquireToSameWindow', 'DefaultZoomFactor', 'WarnWhenUnsaved', 'Calibrated',
            'LowerLUTIsZero', 'AutoLUT', 'AutoLUTInLive', 'AutoLUTInROI', 'HorizontalRuler',
            'VerticalRuler', 'FixedITEXHeader']
        self.parameters['Images'] = {
            'get': 'ImgParamGet',
            'set': 'ImgParamSet',
            'info': 'ImgParamGet',
            'value': {
                key: None for key in img_params}}

        # QUICK PROFILE
        quick_profile_params = [
            'UseMinAsZero', 'DisplayQPOutOfImage', 'QPRelativeSpace', 'DisplayDirectionForRect',
            'AdjustQPHeight', 'DisplayFWHM', 'DoGaussFit', 'FWHMColor', 'FWHMSize', 'FWHMNoOfDigis']
        self.parameters['QuickProfile'] = {
            'get': 'QprParamGet',
            'set': 'QprParamSet',
            'info': 'QprParamInfo',
            'value': {
                key: None for key in quick_profile_params}}

        # LUT
        LUT_params = [
            'Limits', 'Cursors', 'Color', 'Inverted', 'Gamma', 'Linearity', 'Overflowcolors']
        self.parameters['LUT'] = {
            'get': 'LutParamGet',
            'set': 'LutParamSet',
            'info': 'LutParamInfo',
            'value': {
                key: None for key in LUT_params}}

        # SEQUENCE
        sequence_params = [
            'AutoCorrectAfterSeq', 'DisplayImgDuringSequence', 'PromptBeforeStart', 'EnableStop',
            'Warning', 'EnableAcquireWrap', 'LoadHISSequence', 'PackHisFiles', 'NeverLoadToRam',
            'LiveStreamingBuffers', 'WrapPlay', 'PlayInterval', 'ProfileNo', 'CorrectionDirection',
            'AcquisitionMode', 'NoOfLoops', 'AcquisitionSpeed', 'AcquireInterval', 'DoAcquireWrap',
            'AcquireImages', 'ROIOnly', 'StoreTo', 'FirstImgToStore', 'DisplayDataOnly',
            'UsedHDSpaceForCheck', 'AcquireProfiles', 'FirstPrfToStore', 'AutoFixpoint',
            'ExcludeSample', 'SampleType', 'CurrentSample', 'NumberOfSamples']
        self.parameters['Sequence'] = {
            'get': 'SeqParamGet',
            'set': 'SeqParamSet',
            'info': 'SeqParamInfo',
            'value': {
                key: None for key in sequence_params}}

        # DEVICES
        dev_params = [
            'TD', 'Streak', 'Streakcamera', 'Spec', 'Spectrograph', 'Del', 'Delay', 'Delaybox',
            'Del1', 'Del2', 'Delay2', 'DelayBox2']
        self.parameters['Devices'] = {
            'get': 'DevParamGet',
            'set': 'DevParamSet',
            'info': 'DevParamInfoEx',
            'value': {
                key: None for key in dev_params}}
        self.list_dev_params()

    def get_parameter(self, base_name=None, sub_level=None, sub_sub_level=None):
        """Get one or more streak parameters.

        If a level is left as ``None``, all values at that point in the hierarchy are
        returned as a nested dictionary.

        Args:
            base_name (str, optional): Top-level group (e.g. ``'Devices'``). ``None``
                returns every parameter.
            sub_level (str, optional): Second-level key (e.g. ``'TD'``).
            sub_sub_level (str, optional): Third-level key (e.g. ``'Time Range'``).

        Returns:
            The parameter value, or a dict of values for the requested subtree.

        Examples:
            ``streak.get_parameter()`` returns all parameters.
            ``streak.get_parameter('Devices', 'TD')`` returns the TD device's settings.

        Note:
            TODO (pre-existing): handle unrecognised/unavailable parameters and devices.
        """
        self._logger.debug('Getting parameter: %s %s %s' % (base_name, sub_level, sub_sub_level))
        if base_name is None:
            return_dict = dict()
            for base_name in self.parameters:
                return_dict[base_name] = self.get_parameter(base_name)
            return return_dict

        command = self.parameters[base_name]['get']
        base_dictionary = self.parameters[base_name]['value']

        if sub_level is not None and sub_sub_level is not None:
            return self.send_command(command, sub_level, sub_sub_level)
        elif sub_sub_level is None:
            sub_dictionary = base_dictionary[sub_level]
            if isinstance(sub_dictionary, dict):
                return_dict = dict()
                for subsublevel in list(sub_dictionary.keys()):
                    return_dict[subsublevel] = self.get_parameter(base_name, sub_level, subsublevel)
                return return_dict
            else:
                return self.send_command(command, sub_level, sub_sub_level)
        else:
            return_dict = dict()
            for sublevel in list(base_dictionary.keys()):
                return_dict[sublevel] = self.get_parameter(base_name, sublevel)
            return return_dict

    def set_parameter(self, base_name, sub_level=None, sub_sub_level=None, value=None):
        """Set one or more streak parameters.

        Args:
            base_name (str): Top-level group (e.g. ``'Camera'``).
            sub_level (str, optional): Second-level key.
            sub_sub_level (str, optional): Third-level key.
            value: A scalar matching the parameter located by the given levels, or a dict
                of key/value pairs to set across the chosen subtree. Must not be ``None``.

        Raises:
            AssertionError: If ``base_name`` is unknown or ``value`` is ``None``.

        Examples:
            ``streak.set_parameter('General', 'ShowStreakControl', None, 1)``
            ``streak.set_parameter('Camera', 'Acquire', 'Exposure', '1 s')``

        Note:
            TODO (pre-existing): handle unrecognised/unavailable parameters and devices.
        """
        self._logger.debug('Setting parameter: %s %s %s %s' %
                           (base_name, sub_level, sub_sub_level, value))
        assert base_name in self.parameters
        assert value is not None  # always need a value
        command = self.parameters[base_name]['set']
        if command is None:
            self._logger.warn('Cannot set %s' % base_name)
            return
        base_dictionary = self.parameters[base_name]['value']

        if sub_level is not None and sub_sub_level is not None:
            self.send_command(command, sub_level, sub_sub_level, value)
        elif sub_sub_level is None:
            sub_dictionary = base_dictionary[sub_level]
            if isinstance(sub_dictionary, dict):
                for sub_sub_level, subsub_value in list(value.items()):
                    assert sub_sub_level in sub_dictionary
                    self.set_parameter(base_name, sub_level, sub_sub_level, subsub_value)
            else:
                self.send_command(command, sub_level, value)
        else:
            for sub_level, values in list(value.items()):
                self.set_parameter(base_name, sub_level, sub_sub_level, values)

    def get_parameter_info(self, base_name, sub_level=None, sub_sub_level=None):
        """Get the descriptor info for one or more streak parameters.

        Args:
            base_name (str): Top-level group.
            sub_level (str, optional): Second-level key.
            sub_sub_level (str, optional): Third-level key.

        Returns:
            The raw info string for the parameter, or a dict of such strings for a subtree.

        Examples:
            ``streak.get_parameter_info('Devices', 'TD', 'Time Range')`` returns a string
            like ``'-1,-1,Time Range,2,2,5,1,2,3,4,5'``.

        Note:
            TODO (pre-existing): parse the reply into more useful structures.
        """
        self._logger.debug('Getting parameter info: %s %s %s' %
                           (base_name, sub_level, sub_sub_level))
        assert base_name in self.parameters
        command = self.parameters[base_name]['info']
        if command is None:
            self._logger.warn('Cannot get info %s' % base_name)
        base_values = self.parameters[base_name]['value']

        if sub_level is not None and sub_sub_level is not None:
            return self.send_command(command, sub_level, sub_sub_level)
        elif sub_sub_level is None:
            sub_values = base_values[sub_level]
            if isinstance(sub_values, dict):
                return_vals = dict()
                for sub_sub_level in list(sub_values.keys()):
                    return_vals[sub_sub_level] = self.get_parameter_info(
                        base_name, sub_level, sub_sub_level)
                return return_vals
            else:
                return self.send_command(command, sub_level, sub_sub_level)
        else:
            return_vals = dict()
            for sub_level in list(base_values.keys()):
                return_vals[sub_level] = self.get_parameter_info(base_name, sub_level)
            return return_vals

    '''General commands'''

    def stop(self):
        """Stop the command currently being executed.

        Note:
            Not currently usable because the VISA communication is locked during commands.
        """
        self.send_command('Stop')

    def shutdown(self):
        """Shut down the application and the RemoteEx program.

        The response is sent before shutdown. This is of limited use once the application has
        hung; recovery in that case must be done by other means (e.g. power-cycling the
        remote computer and restarting RemoteEx from autostart).
        """
        self.send_command('Shutdown')

    '''Application commands'''

    def start_app(self, visible=1, ini_file=None):
        """Start the HPDTA application on the remote computer.

        If already running, returns immediately; otherwise waits until startup completes
        (the timeout is raised to 2 minutes for this).

        Args:
            visible (int or bool): ``0``/``False`` starts an invisible application (no
                window on the remote computer); any other value starts it visibly. Ignored
                if the application is already running.
            ini_file (str, optional): If given, start with this INI file (RemoteEx 8.3.0+).
                Also ignored if the application is already running.
        """
        timeout = self.instr.timeout
        self.instr.timeout = 120000

        if ini_file is not None:
            self.send_command('AppStart', visible, ini_file)
        else:
            self.send_command('AppStart', visible)

        self.instr.timeout = timeout

    '''Acquisition commands'''

    def start_acquisition(self, mode='Acquire', wait=True):
        """Start an acquisition.

        Args:
            mode (str): One of ``'Live'`` (live mode), ``'Acquire'`` (acquire mode),
                ``'AI'`` (analog integration) or ``'PC'`` (photon counting).
            wait (bool): If ``True``, block until the acquisition has finished.
        """
        self.send_command('AcqStart', mode)
        if wait:
            while self.is_acquisition_busy():
                time.sleep(0.1)

    def is_acquisition_busy(self):
        """Report whether an acquisition is currently running.

        Returns:
            bool: ``True`` if busy, ``False`` if idle.

        Raises:
            ValueError: If the reported status is not recognised.
        """
        reply = self.send_command('AcqStatus').split(',')
        if reply[0] == 'idle':
            return False
        elif reply[0] == 'busy':
            return True
        else:
            raise ValueError('Unrecognised status: %s' % reply)

    def stop_acquisition(self, timeout=1000):
        """Stop the currently running acquisition.

        Args:
            timeout (int): Milliseconds to wait for the acquisition to end, in the range
                [1...60000] (RemoteEx 8.2.0 pf5+). Defaults to 1000.

        Note:
            TODO (pre-existing): get the AcquisitionStop/SequenceStop functionality working,
            perhaps with background threads. The reply is ``0,AcqStop`` on success or
            ``7,AcqStop,timeout`` if it times out waiting for the stop.
        """
        self.send_command('AcqStop', timeout)

    '''Camera commands'''

    def get_live_bkg(self):
        """Capture a new background image for real-time background subtraction (RTBS).

        Only available while LIVE mode is running.
        """
        self.send_command('CamGetLiveBG')

    '''External device commands (HPD-TA only)'''

    def list_dev_params(self, devices=None):
        """Query the connected devices for their parameters and store them in self.parameters.

        Devices reported as unavailable (error code 7) are marked ``'NotAvailable'``.

        Args:
            devices (iterable, optional): One or more device names from ``['TD', 'Streak',
                'Streakcamera', 'Spec', 'Spectrograph', 'Del', 'Delay', 'Delaybox', 'Del1',
                'Del2', 'Delay2', 'DelayBox2']``. Defaults to all known devices.

        Raises:
            ValueError: If a requested device name is not recognised.
            StreakError: For SDK errors other than "not available".
        """
        if devices is None:
            devices = list(self.parameters['Devices']['value'].keys())
        for device in devices:
            if device not in list(self.parameters['Devices']['value'].keys()):
                raise ValueError('Device %s not recognised' % device)
            try:
                reply = self.send_command('DevParamsList', device)
                param_list = reply.split(',')[1:]

                self.parameters['Devices']['value'][device] = {key: None for key in param_list}
            except StreakError as e:
                if e.error_code == 7:
                    self.parameters['Devices']['value'][device] = 'NotAvailable'
                else:
                    raise e

    '''Auxiliary devices commands'''
    '''Correction commands'''

    def do_correction(self, destination='Current', type='BacksubShadingCurvature'):
        """Apply image corrections to an image.

        Args:
            destination (str or int): ``'Current'`` or an image number between 0 and 19.
            type (str): One of ``['Backsub', 'Background', 'Shading', 'Curvature',
                'BacksubShading', 'BacksubCurvature', 'BacksubShadingCurvature',
                'DefectCorrect']``.

        Raises:
            NotImplementedError: If ``type`` is ``'DefectCorrect'``.
        """
        if type == 'DefectCorrect':
            raise NotImplementedError
        self.send_command('CorDoCorrection', destination, type)

    '''Processing commands'''
    '''Defect pixel tool commands'''
    '''Image commands'''

    def save_image(self,
                   image_index='Current',
                   image_type='TIF',
                   filename='DefaultImage.tif',
                   overwrite=False,
                   directory=None):
        """Save an image to disk on the remote computer.

        Args:
            image_index (str or int): Image to save, ``'Current'`` or a number 0-19.
            image_type (str): One of ``'IMG'`` (ITEX), ``'TIF'``, ``'TIFF'``, ``'ASCII'``,
                ``'data2tiff'``, ``'data2tif'``, ``'display2tiff'``, ``'display2tif'``.
            filename (str): File name or path. Relative names are joined to ``directory``.
            overwrite (bool): Whether to overwrite an existing file.
            directory (str, optional): Directory for relative filenames; defaults to the cwd.
        """
        if directory is None:
            directory = os.getcwd()
        if not os.path.isabs(filename):
            filename = os.path.join(directory, filename)
        self.send_command('ImgSave', image_index, image_type, filename, int(overwrite))

    def load_image(self, filename='DefaultImage.txt', image_type='ASCII'):
        """Load an image from disk into a new window.

        Not all saveable file types can be loaded; some are export-only. The image is always
        loaded into a new window regardless of the AcquireToSameWindow option, and an error
        is returned if the maximum number of windows is reached.

        Args:
            filename (str): File name or path; relative names are joined to the cwd.
            image_type (str): One of ``'IMG'`` (ITEX), ``'TIF'``, ``'TIFF'``, ``'ASCII'``,
                ``'data2tiff'``, ``'data2tif'``, ``'display2tiff'``, ``'display2tif'``.
        """
        if not os.path.isabs(filename):
            filename = os.path.join(os.getcwd(), filename)
        self.send_command('ImgLoad', image_type, filename)

    def delete_image(self, image_index='Current'):
        """Delete image(s) from memory (not from disk).

        Deletes the specified images whether or not their content has been saved; save first
        if you want to keep them.

        Args:
            image_index (str or int): ``'Current'``, ``'All'`` or a number 0-19.
        """
        self.send_command('ImgDelete', image_index)

    def get_image_status(self, image_index='Current', *identifiers):
        """Get and parse the status header of an image.

        Args:
            image_index (str or int): ``'Current'`` or a number 0-19.
            *identifiers: Optional section identifier and (optionally) token identifier to
                narrow the query.

        Returns:
            dict: Nested ``{section: {key: value}}`` dictionary parsed from the reply.

        Raises:
            ValueError: If more than two identifiers are supplied.
        """
        if len(identifiers) == 0:
            reply = self.send_command('ImgStatusGet', image_index, 'All')
        elif len(identifiers) == 1:
            reply = self.send_command('ImgStatusGet', image_index, 'Section', identifiers[0])
        elif len(identifiers) == 2:
            reply = self.send_command('ImgStatusGet', image_index, 'Token', identifiers[0],
                                      identifiers[1])
        else:
            raise ValueError('Too many parameters')

        # Split the large string into sections that start with a word within square parenthesis followed by a comma, and
        # then a bunch of other things until the next square parenthesis
        sections = re.findall('\[(.+?)\],([^\[]+)', reply)
        parsed_reply = dict()
        for section_title, section in sections:
            parsed_reply[section_title] = dict()
            # Divide the section into substrings of "something=something", separated by commas or the end of the line
            subsections = re.findall('(.+?)="?(.+?)"?[,"$]', section)
            for subsection, value in subsections:
                parsed_reply[section_title][subsection] = value

        return parsed_reply

    @property
    def current_index(self):
        """Index of the currently selected image window."""
        return int(self.send_command('ImgIndexGet'))

    @current_index.setter
    def current_index(self, index):
        self.send_command('ImgIndexSet', index)

    @property
    def default_directory(self):
        """Default directory used by the remote application for image files."""
        return self.send_command('ImgDefaultDirGet')

    @default_directory.setter
    def default_directory(self, path):
        self.send_command('ImgDefaultDirSet', path)

    def get_img_info(self, image_index='Current'):
        """Return the size and pixel depth of an image.

        Args:
            image_index (str or int): ``'Current'`` or an image number.

        Returns:
            tuple: ``(shape, bytes_per_pixel)`` where ``shape`` is a 4-element list of pixel
            bounds and ``bytes_per_pixel`` is the size of a single pixel.
        """
        response = self.send_command('ImgDataInfo', image_index, 'Size')
        response = [int(x) for x in response.split(',')]
        shape = response[:4]
        bytes_per_pixel = response[-1]
        return shape, bytes_per_pixel

    def get_image_data(self, image_index='Current', type='Data', *profile_params):
        """Request image, display or profile data over the second TCP-IP channel.

        An error is issued by the camera if the data channel is unavailable.

        Args:
            image_index (str or int): ``'Current'`` or a number 1-19.
            type (str): ``'Data'`` (raw, 1/2/4 BPP), ``'Display'`` (1 BPP) or ``'Profile'``
                (4-byte floats).
            *profile_params: For ``'Profile'``, five numbers: profile type (1 line, 2
                horizontal bin, 3 vertical bin) and coordinates iX, iY, iDX, iDY.
        """
        if type != 'Profile':
            self.send_command('ImgDataGet', image_index, type)
        else:
            self.send_command('ImgDataGet', image_index, type, *profile_params)

    def dump_image_data(self, path, image_index='Current', type='Data', *profile_params):
        """Write image, display or profile data to a binary file (no header) on the remote PC.

        An alternative to fetching data over the second TCP-IP port.

        Args:
            path (str): Destination file path on the remote computer.
            image_index (str or int): ``'Current'`` or an image number.
            type (str): ``'Data'`` (raw, 1/2/4 BPP), ``'Display'`` (1 BPP) or ``'Profile'``
                (4-byte floats).
            *profile_params: For ``'Profile'``, five numbers: profile type (1 line, 2
                horizontal bin, 3 vertical bin) and coordinates iX, iY, iDX, iDY.
        """
        if type != 'Profile':
            self.send_command('ImgDataDump', image_index, type, path)
        else:
            profile_type = profile_params[0]
            iX = profile_params[1]
            iY = profile_params[2]
            iDX = profile_params[3]
            iDY = profile_params[4]
            self.send_command('ImgDataDump', image_index, type, profile_type, iX, iY, iDX, iDY,
                              path)

    '''Quick profile commands'''
    '''LUT commands'''

    def auto_lut(self):
        """Automatically sets the LUT of the current image"""
        return self.send_command('LutSetAuto')

    '''Sequence commands'''

    def start_sequence(self, directory=None, wait=False):
        """Start a streak sequence acquisition.

        Args:
            directory (str, optional): If given, sequence images are automatically saved to
                this directory on the remote computer.
            wait (bool): If ``True``, block until the acquisition has finished.
        """
        if directory is not None:
            self.set_parameter('Sequence', 'StoreTo', 'HD <individual files - all modes>')
            self.set_parameter('Sequence', 'FirstImgToStore', directory)
        self.send_command('SeqStart')

        if wait:
            while self.is_sequence_busy():
                time.sleep(0.5)

    def stop_sequence(self):
        """Stop the currently running sequence acquisition."""
        self.send_command('SeqStop')

    def is_sequence_busy(self):
        """Report whether a sequence is currently running.

        Returns:
            bool: ``True`` if busy, ``False`` if idle.

        Raises:
            ValueError: If the reported status is not recognised.
        """
        reply = self.send_command('SeqStatus')
        split_reply = reply.split(',')
        if split_reply[0] == 'idle':
            return False
        elif split_reply[0] == 'busy':
            return True
        else:
            raise ValueError('Unrecognised sequence status: %s' % reply)

    def delete_sequence(self):
        """Delete the current sequence from memory (not from the hard disk)."""
        self.send_command('SeqDelete')

    def save_sequence(self, image_type='ASCII', filename='DefaultSequence.txt', overwrite=0):
        """Save the current sequence to disk on the remote computer.

        Args:
            image_type (str): File type to write (e.g. ``'ASCII'``).
            filename (str): File name or path; relative names are joined to the cwd.
            overwrite: Whether to overwrite an existing file.
        """
        if not os.path.isabs(filename):
            filename = os.path.join(os.getcwd(), filename)
        self.send_command('SeqSave', image_type, filename, overwrite)

    def load_sequence(self, image_type='ASCII', filename='DefaultSequence.txt'):
        """Load a sequence from disk on the remote computer.

        Args:
            image_type (str): File type to read (e.g. ``'ASCII'``).
            filename (str): File name or path; relative names are joined to the cwd.
        """
        if not os.path.isabs(filename):
            filename = os.path.join(os.getcwd(), filename)
        self.send_command('SeqLoad', image_type, filename)

    '''My commands'''

    def capture(self, mode='Acquire', save=False, delete=False, save_kwargs=None):
        """Acquire an image (or sequence) and optionally return it as a numpy array.

        In ``'Acquire'`` mode, unless ``save`` is set the pixel data is read back over the
        data socket and returned as a 2D array. In ``'Sequence'`` mode the sequence is run
        (and optionally deleted) but no array is returned.

        Args:
            mode (str): ``'Acquire'`` or ``'Sequence'``.
            save (bool): If ``True``, save the image instead of reading it back.
            delete (bool): If ``True``, delete the image/sequence after handling it.
            save_kwargs (dict, optional): Keyword arguments forwarded to :meth:`save_image`
                when ``save`` is set.

        Returns:
            numpy.ndarray or None: The captured image in ``'Acquire'`` read-back mode,
            otherwise ``None``.

        Raises:
            ValueError: If ``mode`` is not recognised.

        Note:
            TODO (pre-existing): test capturing and returning a sequence.
        """
        if mode == 'Acquire':
            self.start_acquisition(mode)

            if save:
                self.save_image(**save_kwargs)
                if delete:
                    self.delete_image()
            else:
                shape, pixel_size = self.get_img_info()
                n_pixels = (shape[2] - shape[0]) * (shape[3] - shape[1])

                self.get_image_data()
                self._logger.debug('Receiving: %s pixels of size %g' % (n_pixels, pixel_size))

                image = []
                for pxl_num in range(n_pixels):
                    pixel = self.data_socket.recv(pixel_size)
                    pixel_value = struct.unpack('h', pixel)[0]
                    image += [pixel_value]
                image = np.array(image).reshape((shape[3] - shape[1], shape[2] - shape[0]))
                if delete:
                    self.delete_image()
                return image
        elif mode == 'Sequence':
            self.start_sequence(wait=True)

            if delete:
                self.delete_sequence()
        else:
            raise ValueError('Capture mode not recognised')


PARAMETER_TYPES = {
    0: 'Boolean',
    1: 'Numeric',
    2: 'List',
    3: 'String',
    4: 'Exposure Time',
    5: 'String'}

ERROR_CODES = {
    0: 'Success',
    1: 'Invalid syntax (command must be followed by parentheses and must have the correct number and type '
       'of parameters separated by comma)',
    2: 'Command or Parameters are unknown.',
    3: 'Command currently not possible',
    4: 'A message during runtime (example: a string indicating the frame rate during live mode)',
    5: 'Reply value of a message box. The structure of RemoteEx does not allow sending inquiry commands '
       'from the RemoteEx to the client. In cases where the standalone program needs to popup a message box '
       'to get some information from the user the RemoteEx just continues execution with the default value '
       'of this message box. When such case happens a string is sent to the RemoteEx Client informing it '
       'about this default value. ',
    6: 'Parameter is missing',
    7: 'Command cannot be executed',
    8: 'An error has occurred during execution',
    9: 'Data cannot be sent by TCP-IP',
    10: 'Value of a parameter is out of range'}
