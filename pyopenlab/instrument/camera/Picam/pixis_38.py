# -*- coding: utf-8 -*-
"""Driver for the Princeton Instruments Pixis CCD camera (64-bit DLL variant).

Variant of the Pixis driver that loads ``picam_64bit.dll``. Communicates with
the Picam DLL, intended for use alongside an Acton spectrometer for Raman
measurements.

Known limitations:
    * Connects to the first camera found. This fails if no camera is connected,
      more than one is connected, or an unexpected camera is connected. Ideally
      the cameras would be iterated and selected by ID, which is awkward because
      the C++ API uses many structures rather than native data types.
    * A camera will not be found if it is in use by another process or has not
      been shut down properly.

Development notes:
    * API for DLL: Picam 5.x Programmers Manual, 4411-0161, Issue 5, August 2018
"""
import ctypes as ct
import logging
import os
import sys
import time

from matplotlib import pyplot as plt
import numpy as np
from picam_constants import PI_V
from picam_constants import PicamConstraintType
from picam_constants import PicamError
from picam_constants import PicamParameter
from picam_constants import PicamSensorTemperatureStatus
from picam_constants import PicamValueType
from picam_constants import transpose_dictionary

from pyopenlab.instrument.camera import Camera

PARENT_DIR = os.path.dirname(os.path.realpath(__file__))


class clsPicamReadoutStruct(ct.Structure):
    """ctypes mirror of the Picam readout struct (data pointer and count)."""
    _fields_ = [("ptr", ct.c_void_p), ("intCount", ct.c_int64)]


class Pixis(Camera):
    """Pixis CCD camera driver backed by the 64-bit Picam DLL."""

    def __init__(self, with_start_up=False, debug=0):
        """Initialise the driver.

        Args:
            with_start_up: If True, open the camera and set a default 10 ms
                exposure immediately.
            debug: Verbosity level; values greater than 0 print debug output.
        """
        self.debug = debug
        self.bolRunning = False
        self.y_max = 0
        self.x_max = 0
        if with_start_up == True:
            self.StartUp()
            self.SetExposureTime(10)

        self.boundary_cut = 5

    def __del__(self):
        if self.bolRunning == True:
            self.ShutDown()

    def raw_snapshot(self, suppress_errors=False):
        """Acquire a single frame (Camera class override).

        Args:
            suppress_errors: If True, return ``(False, None)`` on failure
                instead of propagating the exception.

        Returns:
            tuple: ``(success, image)`` where ``image`` is a numpy array.

        Raises:
            Exception: Re-raises any acquisition error when ``suppress_errors``
                is False.
        """
        try:
            image = self.GetCurrentFrame()
            return True, image
        except Exception as e:
            if suppress_errors == True:
                return False, None
            else:
                raise e

    def get_roi(self, x_min=0, x_max=None, y_min=0, y_max=None, suppress_errors=False, debug=0):
        """Acquire a frame and crop it to a region of interest.

        Args:
            x_min: Left column of the ROI.
            x_max: Right column of the ROI; defaults to the sensor width.
            y_min: Top row of the ROI.
            y_max: Bottom row of the ROI; defaults to the sensor height.
            suppress_errors: Forwarded to :meth:`raw_snapshot`.
            debug: Verbosity level; values greater than 0 print debug output.

        Returns:
            numpy.ndarray: The cropped image.
        """
        _, raw_image = self.raw_snapshot(suppress_errors=suppress_errors)
        if x_max is None:
            x_max = self.x_max
        if y_max is None:
            y_max = self.y_max

        if debug > 0:
            print("Pixis.get_roi region of interest:", x_min, x_max, y_min, y_max)
        roi_image = raw_image[max(0, y_min):min(y_max, self.y_max),
                              max(0, x_min):min(self.x_max, x_max)]
        if debug > 0:
            print("Pixis.roi_image.shape:", roi_image.shape)
        return roi_image

    def get_spectrum(self,
                     x_min=0,
                     x_max=None,
                     y_min=0,
                     y_max=None,
                     with_boundary_cut=True,
                     suppress_errors=False):
        """Acquire a frame and reduce the ROI to a 1D spectrum.

        The spectrum is the column-wise mean of the ROI. Edge pixels are
        optionally discarded to remove edge effects.

        Args:
            x_min: Left column of the ROI.
            x_max: Right column of the ROI; defaults to the sensor width.
            y_min: Top row of the ROI.
            y_max: Bottom row of the ROI; defaults to the sensor height.
            with_boundary_cut: If True, trim ``boundary_cut`` pixels from each
                end of the spectrum.
            suppress_errors: Forwarded to :meth:`get_roi`.

        Returns:
            tuple: ``(spectrum, pixel_offsets)`` numpy arrays, where
            ``pixel_offsets`` is measured from the frame centre.
        """
        roi_image = self.get_roi(x_min, x_max, y_min, y_max, suppress_errors)
        #cut edge values from raw spectrum - remove edge effects
        raw_spectrum = np.mean(roi_image, axis=0)
        pixel_offsets = np.array(list(range(0, len(raw_spectrum)))) - int(self.FrameWidth / 2)
        if with_boundary_cut == True:
            return raw_spectrum[self.boundary_cut:-self.
                                boundary_cut], pixel_offsets[self.boundary_cut:-self.boundary_cut]

        else:
            return raw_spectrum, pixel_offsets

    def get_parameter(self, parameter_name, label="unknown"):
        """Read a camera parameter via the appropriate Picam getter.

        Args:
            parameter_name: Parameter name as defined in ``picam_constants.py``.
            label: Human-readable label used only in error messages.

        Returns:
            The parameter value, or ``numpy.nan`` if the DLL call fails.

        Raises:
            AssertionError: If the parameter or its types are not recognised.
            ValueError: If no getter function exists for the parameter.
            NotImplementedError: For value types not yet supported (Enumeration,
                Rois, Pulse, Modulations).
        """

        if self.debug > 0:
            print("pixis.get_parameter::parameter_name:{}".format(parameter_name))
        self.picam.PicamAdvanced_RefreshParametersFromCameraDevice(self.CameraHandle)
        assert (parameter_name in list(PicamParameter.keys())
                )  #Check that the passed parameter name is valid (ie. in constants file)
        param_type, constraint_type, n = PicamParameter[parameter_name]
        if self.debug > 0:
            print("pixis:get_parameter::param_type: {}".format(param_type))
            print("pixis:get_parameter::constraint_type: {}".format(constraint_type))
            print("pixis:get_parameter::n: {}".format(n))

        param_id = PI_V(value_type=param_type, constraint_type=constraint_type, parameter_index=n)

        #assert returned parameter value type is valid one
        valid_value_types = list(transpose_dictionary(PicamValueType).keys())
        assert (param_type in valid_value_types)

        #assert returned parameter constraint type is valid one
        valid_constraint_types = list(transpose_dictionary(PicamConstraintType).keys())
        assert (constraint_type in valid_constraint_types)

        paramtype = param_type.replace("PicamValueType_", "")

        if self.debug > 0:
            print("paramtype:", paramtype)

        if paramtype == "Enumeration":
            paramtype = "IntegerValue"

        else:
            paramtype = paramtype + "Value"

        function_name = "Picam_GetParameter{}".format(paramtype)
        if self.debug > 0:
            print("Function name:", function_name)
            print("Parameter name:", parameter_name)
            print("Parameter id:", param_id)
            # print "Function object", f

        getter = getattr(self.picam, function_name, None)
        if getter is None:
            raise ValueError("Getter is none!")
        else:
            if self.debug > 0:
                print(getter)
        temp = {
            "PicamValueType_Integer": ct.c_int(),
            "PicamValueType_Boolean": ct.c_bool(),
            "PicamValueType_LargeInteger": ct.c_long(),
            "PicamValueType_FloatingPoint": ct.c_double(),
            "PicamValueType_Enumeration": ct.c_int(),  #TODO 
            "PicamValueType_Rois": None,  #TODO
            "PicamValueType_Pulse": None,  #TODO
            "PicamValueType_Modulations": None  #None       
        }

        value = temp[param_type]
        if self.debug > 0:
            print("pixis.get_parameter::param_type: {}".format(param_type))
            print("pixis.get_parameter::value: {}".format(value))
        if value is not None:
            response = getter(self.CameraHandle, param_id, ct.pointer(value))

            if response != 0:
                print(("Could not GET value of parameter {0} [label:{1}]".format(
                    parameter_name, label)))
                print(("[Code:{0}] {1}".format(response, PicamError[response])))
                return np.nan

            return value.value
        else:
            '''
            Cases left to implement:
                PicamValueType_Enumeration,
                PicamValueType_Rois,
                PicamValueType_Pulse,
                PicamValueType_Modulations
            '''
            raise NotImplementedError()

    def set_parameter(self, parameter_name, parameter_value):
        """Write a camera parameter and commit it via the Picam setter.

        Args:
            parameter_name: Parameter name as defined in ``picam_constants.py``.
            parameter_value: Value to write; coerced to the parameter's ctype.

        Returns:
            None on success, or ``numpy.nan`` if the DLL call fails.

        Raises:
            AssertionError: If the parameter/types are unrecognised or the
                commit is not accepted by the camera.
            NotImplementedError: For value types not yet supported (Enumeration,
                Rois, Pulse, Modulations).
        """
        assert (parameter_name in list(PicamParameter.keys())
                )  #Check that the passed parameter name is valid (ie. in constants file)
        param_type, constraint_type, n = PicamParameter[parameter_name]
        param_id = PI_V(value_type=param_type, constraint_type=constraint_type, parameter_index=n)

        #assert returned parameter value type is valid one
        valid_value_types = list(transpose_dictionary(PicamValueType).keys())
        assert (param_type in valid_value_types)

        #assert returned parameter constraint type is valid one
        valid_constraint_types = list(transpose_dictionary(PicamConstraintType).keys())
        assert (constraint_type in valid_constraint_types)

        function_name = "Picam_SetParameter{}Value".format(param_type.replace(
            "PicamValueType_", ""))
        setter = getattr(self.picam, function_name)
        # setter = self.picam.Picam_SetParameterFloatingPointValue
        if self.debug > 0:
            print("Function name:", function_name)
            print("Paramer type, Constraint type, n:", param_type, constraint_type, n)
            print("Function object", setter)

        temp = {
            "PicamValueType_Integer": ct.c_int,
            "PicamValueType_Boolean": ct.c_bool,
            "PicamValueType_LargeInteger": ct.c_long,
            "PicamValueType_FloatingPoint":
                ct.
                c_double,  #WARNING - THIS SHOULD BE A DOUBLE (64bit), NOT FLOAT (32bit) [for 32bit change to float]
            "PicamValueType_Enumeration": ct.c_int,  #Maybe an int 
            "PicamValueType_Rois": None,  #TODO
            "PicamValueType_Pulse": None,  #TODO
            "PicamValueType_Modulations": None  #None       
        }

        #allocate memory for parameter for DLL to populate
        value = temp[param_type](parameter_value)

        if value is not None:
            if self.debug > 0:
                print("setting: param_id:  {0}, value:{1}".format(param_id, value))

            response = setter(self.CameraHandle, param_id, value)
            if response != 0:
                print(("Could not SET value of parameter {0}".format(parameter_name)))
                print(("[Code:{0}] {1}".format(response, PicamError[response])))
                return np.nan
            #check if commit failed
            failed_commit = (ct.c_int * 10)()
            failed_count = ct.c_int()
            response = self.picam.Picam_CommitParameters(self.CameraHandle, ct.byref(failed_commit),
                                                         ct.byref(failed_count))
            if self.debug > 0:
                print("Picam_CommitParameters response:", response, failed_count,
                      list(failed_commit))

            assert (int(failed_count.value) == 0)
            #check if commit has passed
            committed = ct.c_bool(False)
            response = self.picam.Picam_AreParametersCommitted(self.CameraHandle,
                                                               ct.byref(committed))
            if self.debug > 0:
                print("Picam_CommitParameters response:", response, committed)

            assert (bool(committed.value) == True)

            return

        else:
            '''
            Cases left to implement:
                PicamValueType_Enumeration,
                PicamValueType_Rois,
                PicamValueType_Pulse,
                PicamValueType_Modulations
            '''
            raise NotImplementedError()

    def StartUp(self):
        """Load the 64-bit Picam DLL, open the first camera and cool to -80 C.

        Populates frame dimensions and sets ``bolRunning``. Returns early
        (without raising) if the DLL or camera cannot be found.
        """
        cint_temp = ct.c_int()
        # Find DLL
        try:
            self.picam = ct.WinDLL(os.path.normpath('{}/picam_64bit.dll'.format(PARENT_DIR)))
            #self.picam = os.add_dll_directory('{}/picam_64bit.dll'.format(PARENT_DIR))
            #self.picam = ct.WinDLL(DLL)
            print(self.picam)
        except Exception as e:
            logging.warning("Error:", e)
            logging.info("Could not find picam dll")
            return
        # Initialise library
        bolInitialised = ct.c_bool(False)
        if self.picam.Picam_InitializeLibrary() != 0:
            print("Could not initialise library")
            return
        self.picam.Picam_IsLibraryInitialized(ct.byref(bolInitialised))
        if bolInitialised == ct.c_bool(False):
            print("Library was not initialised")
            return
        # Get camera handle
        self.CameraHandle = ct.c_void_p()
        if self.picam.Picam_OpenFirstCamera(ct.byref(self.CameraHandle)) != 0:
            print("Could not find camera")
            return

        self.x_max = self.FrameWidth = self.get_parameter(
            parameter_name="PicamParameter_SensorActiveWidth", label="frame width")
        self.y_max = self.FrameHeight = self.get_parameter(
            parameter_name="PicamParameter_SensorActiveHeight", label="frame height")
        print("Frame size:", self.x_max, self.y_max)
        self.bolRunning = True
        self.SetTemperatureWithLock(-80.0)

    def ShutDown(self):
        """Close the camera and uninitialise the Picam library."""
        if self.bolRunning == False:
            return
        if self.picam.Picam_CloseCamera(self.CameraHandle) != 0:
            print("Could not close camera")
            return
        if self.picam.Picam_UninitializeLibrary() != 0:
            print("Could not shut down library")
            return
        self.bolRunning = False

    def SetExposureTime(self, time):
        """Set the exposure time.

        Args:
            time: Exposure time in milliseconds.
        """
        param_name = "PicamParameter_ExposureTime"
        param_value = time  #in milliseconds
        self.set_parameter(parameter_name=param_name, parameter_value=param_value)

    def SetTemperatureWithLock(self, temperature):
        """Set the sensor set-point and block until the temperature locks.

        Args:
            temperature: Target sensor temperature in degrees Celsius.

        Note:
            This method references the module-level global ``p`` (defined only
            in the ``__main__`` block) instead of ``self``, so it raises
            ``NameError`` when used as an instance method outside that script.
        """
        self.__SetSensorTemperatureSetPoint(temperature)
        status_code = p.GetTemperatureStatus()
        while PicamSensorTemperatureStatus[status_code] != "PicamSensorTemperatureStatus_Locked":
            print("TemperatureStatus: {3}[{2}] (current: {0}, target:{1})".format(
                p.GetSensorTemperatureReading(), temperature, status_code,
                PicamSensorTemperatureStatus[status_code]))
            time.sleep(0.5)
            status_code = p.GetTemperatureStatus()

        status_code = p.GetTemperatureStatus()
        print("TemperatureStatus: {0} [{1}]".format(PicamSensorTemperatureStatus[status_code],
                                                    status_code))
        return

    def GetSensorTemperatureReading(self):
        """Return the current sensor temperature reading in degrees Celsius."""
        param_name = "PicamParameter_SensorTemperatureReading"
        return self.get_parameter(param_name)

    def __SetSensorTemperatureSetPoint(self, temperature):
        """Set the sensor temperature set-point without waiting for a lock.

        Use :meth:`SetTemperatureWithLock` instead if you need to wait for the
        temperature to stabilise.

        Args:
            temperature: Target sensor temperature in degrees Celsius.
        """
        param_name = "PicamParameter_SensorTemperatureSetPoint"
        return self.set_parameter(parameter_name=param_name, parameter_value=temperature)

    def GetTemperatureStatus(self):
        """Return the sensor temperature status code.

        See ``picam_constants.PicamSensorTemperatureStatus`` for the
        int-to-status mapping.
        """
        param_name = "PicamParameter_SensorTemperatureStatus"
        return self.get_parameter(param_name)

    def GetExposureTime(self):
        """Return the current exposure time in milliseconds."""
        param_name = "PicamParameter_ExposureTime"
        #function call: PicamEnumeratedType_CoolingFanStatus
        return self.get_parameter(parameter_name=param_name)

        # return self.get_parameter(parameter=33685527, label="exposure time")

    def GetSensorType(self):
        """Return the sensor type code."""
        param_name = "PicamParameter_SensorType"
        return self.get_parameter(parameter_name=param_name)

    def GetIntensifierStatus(self):
        """Return the intensifier status code."""
        param_name = "PicamParameter_IntensifierStatus"
        return self.get_parameter(parameter_name=param_name)

    def GetCurrentFrame(self):
        """Acquire one frame and return it as a numpy array.

        Starts the camera first if it is not already running.

        Returns:
            numpy.ndarray: The acquired frame, or ``None`` if acquisition fails.
        """
        if self.bolRunning == False:
            self.StartUp()

        structReadout = clsPicamReadoutStruct()
        intErrorMask = ct.c_int()

        # Read in pointer to image buffer
        if self.picam.Picam_Acquire(self.CameraHandle, 1, -1, ct.byref(structReadout),
                                    ct.byref(intErrorMask)) != 0:
            print("Image acquisition failed")
            return
        if intErrorMask.value != 0:
            print("Image acquisition returned an error")
            return

        # Get image
        ctarr = (ct.c_uint16 * (self.FrameWidth * self.FrameHeight))  # Create ctypes array
        ctarr = ctarr.from_address(structReadout.ptr)  # Read in array from pointer
        nparr = np.array(ctarr)  # Convert to numpy array
        nparr = nparr.reshape((self.FrameWidth, self.FrameHeight))  # Reshape numpy array

        return nparr


if __name__ == "__main__":

    p = Pixis(debug=0)
    p.StartUp()

    # p.SetExposureTime(100)
    # p.GetExposureTime()
    # print p.GetExposureTime()
    # print p.GetTemperature()

    p.SetTemperatureWithLock(-75)
    # import time

    # for i in range(500):

    #     # p.picam.PicamAdvanced_RefreshParameterFromCameraDevice(17039376)
    #     # p.picam.PicamAdvanced_RefreshParameterFromCameraDevice(16908303)
    #     print i,p.GetSensorTemperatureReading(), p.GetTemperatureStatus()

    #     time.sleep(0.5)
    #     # import sys
    # sys.exit(0)

    # for i in range(10):

    #     print i
    #     s = p.GetSensorTemperatureReading()
    #     print "value:", s

    #     time.sleep(0.5)

    # print p.GetSensorTemperatureReading()
    # print p.GetExposureTime()
    # p.SetExposureTime(50.0)
    # print p.GetExposureTime()

    # _,Frame = p.raw_snapshot()
    # print p.GetExposureTime()

    # p.SetExposureTime(100.0)
    # _,Frame = p.raw_snapshot()
    # print p.GetExposureTime()

    # p.SetExposureTime(200.0)
    # _,Frame = p.raw_snapshot()
    # print p.GetExposureTime()

    # p.SetExposureTime(400.0)
    # _,Frame = p.raw_snapshot()
    # print p.GetExposureTime()

    # p.SetExposureTime(800.0)
    # _,Frame = p.raw_snapshot()
    # print p.GetExposureTime()

    p.ShutDown()

    # plt.imshow(Frame, cmap='gray')
    # plt.show()
