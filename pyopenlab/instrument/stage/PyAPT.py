# -*- coding: utf-8 -*-
"""Thorlabs APT motor controller via the proprietary APT.dll (ctypes wrapper).

This wraps Thorlabs' ``APT.dll`` directly through ctypes (as opposed to the
serial APT protocol in ``apt_vcp_motor.py``). The correct 32- or 64-bit DLL is
selected from ``DLL/<arch>/APT.dll`` based on the Python interpreter's word
length. On 64-bit machines the DLL additionally requires ``mfc110.dll`` from the
"Microsoft Visual C++ Redistributable for Visual Studio 2012 Update 4".
"""
from ctypes import c_buffer
from ctypes import c_float
from ctypes import c_long
from ctypes import pointer
from ctypes import windll
import os
import platform

DEBUG = False

PARENT_DIR = os.path.dirname(os.path.abspath(__file__))
if DEBUG:
    print("Current working directory: ", os.getcwd())
    print("PyAPT.py file parent directory: ", PARENT_DIR)
    #determine system type by looking at python executable
    #source: https://docs.python.org/2/library/platform.html
    print("Platform architecture: ", platform.architecture())

OS_TYPE = platform.architecture()[0]
assert (OS_TYPE in ["32bit",
                    "64bit"]), "Cannot determine type of operating system from python executable"
DLL_PATH = os.path.normpath('{0}/DLL/{1}/APT.dll'.format(PARENT_DIR, OS_TYPE))

if DEBUG:
    print("Word length of OS [32/64bit]", OS_TYPE)
    print("APT DLL path:", DLL_PATH)


class APTMotor(object):
    """Thorlabs APT motor controlled through ``APT.dll`` via ctypes.

    Distances are in millimetres and velocities in mm/s, matching the DLL's
    floating-point API. The ``mb*`` methods add a backlash correction
    (``blCorr``) by approaching the target from a consistent direction.
    """

    def __init__(self,
                 SerialNum=None,
                 HWTYPE=31,
                 blacklash_correction=0.10,
                 minimum_velocity=0.0,
                 acceleration=5.0,
                 max_velocity=10.0):
        """Load the APT DLL, initialise it and optionally connect to a device.

        Args:
            SerialNum: Device serial number; if given, the hardware is
                initialised immediately, otherwise call ``setSerialNumber`` and
                ``initializeHardwareDevice`` later.
            HWTYPE: APT hardware type code (default 31, TDC001 DC servo T-Cube).
                Common codes: 11/12 BSC001/101 (1-ch stepper), 13 BSC002 (2-ch
                stepper), 14 BDC101 (1-ch DC servo), 21 SCC001 (stepper card),
                22 DCC001 (DC servo card), 24 ODC001 (DC servo cube), 25 OST001
                (stepper cube), 26 MST601 (2-ch stepper module), 29 TST001
                (stepper T-Cube), 31 TDC001 (DC servo T-Cube), 42 LTSxxx,
                43 L490MZ, 44 BBD10x (brushless DC servo).
            blacklash_correction: Backlash correction distance in mm (note the
                misspelled parameter name is preserved for compatibility).
            minimum_velocity: Minimum (start) velocity in mm/s.
            acceleration: Acceleration in mm/s^2.
            max_velocity: Maximum velocity in mm/s.
        """
        self.Connected = False

        self.aptdll = windll.LoadLibrary(DLL_PATH)

        self.aptdll.EnableEventDlg(True)
        self.aptdll.APTInit()
        #print 'APT initialized'
        self.HWType = c_long(HWTYPE)
        self.blCorr = blacklash_correction  #100um backlash correction
        if SerialNum is not None:
            if DEBUG:
                print(("Serial is", SerialNum))
            self.SerialNum = c_long(SerialNum)
            self.initializeHardwareDevice()
        # TODO : Error reporting to know if initialisation went sucessfully or not.

        else:
            if DEBUG:
                print("No serial, please setSerialNumber")

        self.setVelocityParameters(minVel=minimum_velocity, acc=acceleration, maxVel=max_velocity)

    def getNumberOfHardwareUnits(self):
        """Return the number of connected HW units available to interface with."""
        numUnits = c_long()
        self.aptdll.GetNumHWUnitsEx(self.HWType, pointer(numUnits))
        return numUnits.value

    def getSerialNumberByIdx(self, index):
        """Return the serial number of the device at the given enumeration index.

        Args:
            index: Zero-based index into the connected devices of this HW type.

        Returns:
            The ``c_long`` holding the serial number (note: not ``.value``).
        """
        HWSerialNum = c_long()
        hardwareIndex = c_long(index)
        self.aptdll.GetHWSerialNumEx(self.HWType, hardwareIndex, pointer(HWSerialNum))
        return HWSerialNum

    def setSerialNumber(self, SerialNum):
        """Store the serial number to use for subsequent DLL calls.

        Args:
            SerialNum: Device serial number.

        Returns:
            The stored serial number as an int.
        """
        if DEBUG:
            print(("Serial is", SerialNum))
        self.SerialNum = c_long(SerialNum)
        return self.SerialNum.value

    def initializeHardwareDevice(self):
        """Initialise the motor so it can be queried and moved.

        The device only responds to position queries and moves once initialised,
        and will not respond to other objects controlling it until released.

        Returns:
            True on success.

        Raises:
            Exception: If the DLL reports a non-zero result (bad serial number
                or connection failure).
        """
        if DEBUG:
            print(('initializeHardwareDevice serial', self.SerialNum))
        result = self.aptdll.InitHWDevice(self.SerialNum)

        if result == 0:
            self.Connected = True
            if DEBUG:
                print('initializeHardwareDevice connection SUCESS')
        # need some kind of error reporting here
        else:
            raise Exception('Connection Failed. Check Serial Number!')
        return True
        ''' Interfacing with the motor settings '''

    def getHardwareInformation(self):
        """Return ``[model, software_version, hardware_notes]`` as byte strings."""
        model = c_buffer(255)
        softwareVersion = c_buffer(255)
        hardwareNotes = c_buffer(255)
        self.aptdll.GetHWInfo(self.SerialNum, model, 255, softwareVersion, 255, hardwareNotes, 255)
        hwinfo = [model.value, softwareVersion.value, hardwareNotes.value]
        return hwinfo

    def getStageAxisInformation(self):
        """Return ``[min_pos, max_pos, units, pitch]`` for the stage axis."""
        minimumPosition = c_float()
        maximumPosition = c_float()
        units = c_long()
        pitch = c_float()
        self.aptdll.MOT_GetStageAxisInfo(self.SerialNum, pointer(minimumPosition),
                                         pointer(maximumPosition), pointer(units), pointer(pitch))
        stageAxisInformation = [
            minimumPosition.value, maximumPosition.value, units.value, pitch.value]
        return stageAxisInformation

    def setStageAxisInformation(self, minimumPosition, maximumPosition):
        """Set the stage axis travel limits (in mm) and lead-screw pitch.

        Args:
            minimumPosition: Minimum allowed position in mm.
            maximumPosition: Maximum allowed position in mm.

        Returns:
            True on success.

        Note:
            The pitch is read from ``self.config.get_pitch()``, but ``self.config``
            is never assigned anywhere in this class, so calling this method
            raises ``AttributeError``. Left as-is (a config object must be set
            on the instance first).
        """
        minimumPosition = c_float(minimumPosition)
        maximumPosition = c_float(maximumPosition)
        units = c_long(1)  #units of mm
        # Get different pitches of lead screw for moving stages for different stages.
        pitch = c_float(self.config.get_pitch())
        self.aptdll.MOT_SetStageAxisInfo(self.SerialNum, minimumPosition, maximumPosition, units,
                                         pitch)
        return True

    def getHardwareLimitSwitches(self):
        """Return ``[reverse_limit_switch, forward_limit_switch]`` settings."""
        reverseLimitSwitch = c_long()
        forwardLimitSwitch = c_long()
        self.aptdll.MOT_GetHWLimSwitches(self.SerialNum, pointer(reverseLimitSwitch),
                                         pointer(forwardLimitSwitch))
        hardwareLimitSwitches = [reverseLimitSwitch.value, forwardLimitSwitch.value]
        return hardwareLimitSwitches

    def getVelocityParameters(self):
        """Return ``[min_velocity, acceleration, max_velocity]`` in mm units."""
        minimumVelocity = c_float()
        acceleration = c_float()
        maximumVelocity = c_float()
        self.aptdll.MOT_GetVelParams(self.SerialNum, pointer(minimumVelocity),
                                     pointer(acceleration), pointer(maximumVelocity))
        velocityParameters = [minimumVelocity.value, acceleration.value, maximumVelocity.value]
        return velocityParameters

    def getVel(self):
        """Return the current maximum velocity in mm/s."""
        if DEBUG:
            print('getVel probing...')
        minVel, acc, maxVel = self.getVelocityParameters()
        if DEBUG:
            print('getVel maxVel')
        return maxVel

    def setVelocityParameters(self, minVel, acc, maxVel):
        """Set the velocity profile.

        Args:
            minVel: Minimum (start) velocity in mm/s.
            acc: Acceleration in mm/s^2.
            maxVel: Maximum velocity in mm/s.

        Returns:
            True on success.
        """
        minimumVelocity = c_float(minVel)
        acceleration = c_float(acc)
        maximumVelocity = c_float(maxVel)
        self.aptdll.MOT_SetVelParams(self.SerialNum, minimumVelocity, acceleration, maximumVelocity)
        return True

    def setVel(self, maxVel):
        """Set the maximum velocity, preserving the current min velocity and acceleration.

        Args:
            maxVel: Maximum velocity in mm/s.

        Returns:
            True on success.
        """
        if DEBUG:
            print(('setVel', maxVel))
        minVel, acc, oldVel = self.getVelocityParameters()
        self.setVelocityParameters(minVel, acc, maxVel)
        return True

    def getVelocityParameterLimits(self):
        """Return ``[max_acceleration, max_velocity]`` allowed by the hardware."""
        maximumAcceleration = c_float()
        maximumVelocity = c_float()
        self.aptdll.MOT_GetVelParamLimits(self.SerialNum, pointer(maximumAcceleration),
                                          pointer(maximumVelocity))
        velocityParameterLimits = [maximumAcceleration.value, maximumVelocity.value]
        return velocityParameterLimits
        '''
        Controlling the motors
        m = move
        c = controlled velocity
        b = backlash correction

        Rel = relative distance from current position.
        Abs = absolute position
        '''

    def getPos(self):
        """Return the current absolute position of the stage in mm.

        Raises:
            Exception: If the device is not connected.
        """
        if DEBUG:
            print('getPos probing...')
        if not self.Connected:
            raise Exception('Please connect first! Use initializeHardwareDevice')

        position = c_float()
        self.aptdll.MOT_GetPosition(self.SerialNum, pointer(position))
        if DEBUG:
            print(('getPos ', position.value))
        return position.value

    def mRel(self, relDistance):
        """Move the motor by a relative distance.

        Args:
            relDistance: Relative distance to move, in mm.

        Returns:
            True on success.
        """
        if DEBUG:
            print(('mRel ', relDistance, c_float(relDistance)))
        if not self.Connected:
            print('Please connect first! Use initializeHardwareDevice')
            #raise Exception('Please connect first! Use initializeHardwareDevice')
        relativeDistance = c_float(relDistance)
        self.aptdll.MOT_MoveRelativeEx(self.SerialNum, relativeDistance, True)
        if DEBUG:
            print('mRel SUCESS')
        return True

    def mAbs(self, absPosition):
        """Move the motor to an absolute position.

        Args:
            absPosition: Target absolute position, in mm.

        Returns:
            True on success.

        Raises:
            Exception: If the device is not connected.
        """
        if DEBUG:
            print(('mAbs ', absPosition, c_float(absPosition)))
        if not self.Connected:
            raise Exception('Please connect first! Use initializeHardwareDevice')
        absolutePosition = c_float(absPosition)
        self.aptdll.MOT_MoveAbsoluteEx(self.SerialNum, absolutePosition, True)
        if DEBUG:
            print('mAbs SUCESS')
        return True

    def mcRel(self, relDistance, moveVel=0.5):
        """Move a relative distance at a controlled velocity, restoring the old velocity after.

        Args:
            relDistance: Relative distance to move, in mm.
            moveVel: Velocity for this move, in mm/s.

        Returns:
            True on success.

        Raises:
            Exception: If the device is not connected.
        """
        if DEBUG:
            print(('mcRel ', relDistance, c_float(relDistance), 'mVel', moveVel))
        if not self.Connected:
            raise Exception('Please connect first! Use initializeHardwareDevice')
        # Save velocities to reset after move
        maxVel = self.getVel()
        # Set new desired max velocity
        self.setVel(moveVel)
        self.mRel(relDistance)
        self.setVel(maxVel)
        if DEBUG:
            print('mcRel SUCESS')
        return True

    def mcAbs(self, absPosition, moveVel=0.5):
        """Move to an absolute position at a controlled velocity, restoring the old velocity after.

        Args:
            absPosition: Target absolute position, in mm.
            moveVel: Velocity for this move, in mm/s.

        Returns:
            True on success.

        Raises:
            Exception: If the device is not connected.
        """
        if DEBUG:
            print(('mcAbs ', absPosition, c_float(absPosition), 'mVel', moveVel))
        if not self.Connected:
            raise Exception('Please connect first! Use initializeHardwareDevice')
        # Save velocities to reset after move
        minVel, acc, maxVel = self.getVelocityParameters()
        # Set new desired max velocity
        self.setVel(moveVel)
        self.mAbs(absPosition)
        self.setVel(maxVel)
        if DEBUG:
            print('mcAbs SUCESS')
        return True

    def mbRel(self, relDistance):
        """Move a relative distance with backlash correction.

        Approaches the target by first moving ``relDistance - blCorr`` then the
        backlash distance ``blCorr``, so the final approach is always in the
        same direction.

        Args:
            relDistance: Relative distance to move, in mm.

        Returns:
            True on success.
        """
        if DEBUG:
            print(('mbRel ', relDistance, c_float(relDistance)))
        if not self.Connected:
            print('Please connect first! Use initializeHardwareDevice')
            #raise Exception('Please connect first! Use initializeHardwareDevice')
        self.mRel(relDistance - self.blCorr)
        self.mRel(self.blCorr)
        if DEBUG:
            print('mbRel SUCCESS')
        return True

    def mbAbs(self, absPosition):
        """Move to an absolute position with backlash correction.

        If the target is below the current position, first overshoots to
        ``absPosition - blCorr`` so the final move approaches from below.

        Args:
            absPosition: Target absolute position, in mm.

        Returns:
            True on success.

        Raises:
            Exception: If the device is not connected.
        """
        if DEBUG:
            print(('mbAbs ', absPosition, c_float(absPosition)))
        if not self.Connected:
            raise Exception('Please connect first! Use initializeHardwareDevice')
        if (absPosition < self.getPos()):
            if DEBUG:
                print(('backlash mAbs', absPosition - self.blCorr))
            self.mAbs(absPosition - self.blCorr)
        self.mAbs(absPosition)
        if DEBUG:
            print('mbAbs SUCCESS')
        return True
        ''' Miscelaneous '''

    def identify(self):
        """Blink the device's active LED to identify it physically."""
        self.aptdll.MOT_Identify(self.SerialNum)
        return True

    def cleanUpAPT(self):
        """Release the APT object; call this when exiting the program."""
        self.aptdll.APTCleanUp()
        if DEBUG:
            print('APT cleaned up')
        self.Connected = False

    def stopMove(self):
        """Stop the current move using a profiled (deceleration) stop.

        Raises:
            Exception: If the device is not connected.
        """
        if DEBUG:
            print(("Stopping stage:{}".format(self.SerialNum)))
        if not self.Connected:
            raise Exception("Not connected to the stage")
        else:
            self.aptdll.MOT_StopProfiled(self.SerialNum)
            if DEBUG:
                print("Stopped")
            return
