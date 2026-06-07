# -*- coding: utf-8 -*-
"""Camera driver for the Thorlabs Kiralux, built on the Thorlabs TSI SDK bindings."""

from functools import wraps
import os
from pathlib import Path
import sys
import threading
import time

import numpy as np

from pyopenlab.instrument.camera import Camera
from pyopenlab.instrument.camera import CameraControlWidget
from pyopenlab.instrument.camera.thorlabs.thorlabs_tsi_sdk.tl_camera import TLCameraSDK
from pyopenlab.instrument.camera.thorlabs.thorlabs_tsi_sdk.tl_camera_enums import SENSOR_TYPE
from pyopenlab.instrument.camera.thorlabs.thorlabs_tsi_sdk.tl_mono_to_color_processor import \
    MonoToColorProcessorSDK
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.notified_property import NotifiedProperty
from pyopenlab.utils.thread_utils import locked_action

dll_path = Path(__file__).parent / 'dlls'
is_64bits = sys.maxsize > 2**32

if is_64bits:
    dll_path /= '64_lib'
else:
    dll_path /= '32_lib'
# this line actually works
os.environ['PATH'] = str(dll_path.absolute()) + os.pathsep + os.environ['PATH']

# this one should, but doesn't
os.add_dll_directory(dll_path.absolute())


def disarmer(f, wait=0.3):
    """Decorate a setter so the camera is disarmed around the call and re-armed afterwards.

    Some properties (ROI, binning, frames-per-trigger, ...) can only be set while the
    camera is disarmed. This wrapper disarms before the call, refreshes the cached image
    dimensions, then re-arms and re-triggers if live view was active. A short ``wait`` is
    needed because the camera takes a moment to accept changes (notably binning).

    Args:
        f: The function (typically a property setter) to wrap.
        wait (float): Seconds to sleep after disarming and after re-triggering.

    Returns:
        The wrapped function.
    """

    @wraps(f)
    def inner_func(self, *args, **kwargs):
        armed = self._camera.is_armed
        if armed:
            self._camera.disarm()
            time.sleep(wait)
        out = f(self, *args, **kwargs)
        self._image_width = self._camera.image_width_pixels
        self._image_height = self._camera.image_height_pixels  # a compromise
        # between querying for every capture and wrapping binx and biny setter
        # methods individually.
        if armed:
            self._camera.arm(2)  # 2 frames to buffer
        if self.live_view:
            self._camera.issue_software_trigger()
            time.sleep(wait)
        return out

    return inner_func


class Kiralux(Camera):
    """Thorlabs Kiralux camera.

    Wraps a Thorlabs TSI SDK camera handle, mirroring its properties onto this class (see
    :meth:`_populate_properties`). Colour (Bayer) sensors are demosaiced via a
    mono-to-colour processor; monochrome sensors return frames unchanged.

    Attributes:
        disarmed_properties: Property names whose setters require the camera to be
            disarmed first.
        notified_properties: Property names surfaced in the GUI.
    """

    disarmed_properties = ('roi', 'binx', 'biny', 'frames_per_trigger_zero_for_unlimited')
    # properties that need the camera to be disarmed to set - there may be more.
    notified_properties = ('gain',)  # properties that are in the gui

    def __init__(self, square_image=False):
        """Open the first available Kiralux camera and arm it for snapshots.

        Args:
            square_image (bool): If ``True``, processed frames are cropped to a square.
        """
        super().__init__()
        self._sdk = TLCameraSDK()
        self._camera = self._sdk.open_camera(self._sdk.discover_available_cameras()[0])

        if self._camera.camera_sensor_type != SENSOR_TYPE.BAYER:
            # Sensor type is not compatible with the color processing library
            def process_frame(f):
                return np.asarray(f)  # no processing for grey images
        else:
            self._mono_to_color_sdk = MonoToColorProcessorSDK()
            self._image_width = self._camera.image_width_pixels
            self._image_height = self._camera.image_height_pixels
            self._mono_to_color_processor = self._mono_to_color_sdk.create_mono_to_color_processor(
                SENSOR_TYPE.BAYER, self._camera.color_filter_array_phase,
                self._camera.get_color_correction_matrix(),
                self._camera.get_default_white_balance_matrix(), self._camera.bit_depth)
            process_frame = self.process_color_frame
        if square_image:
            self.process_frame = lambda f: self.make_square(process_frame(f))
        else:
            self.process_frame = process_frame
        self._bit_depth = self._camera.bit_depth
        self._camera.image_poll_timeout_ms = 0
        self._populate_properties()

        self._camera.frames_per_trigger_zero_for_unlimited = 1  # snapshot mode
        self._camera.arm(2)

    def _populate_properties(self):
        """Copy the underlying TLCamera's properties onto this class for direct access.

        Each property of the wrapped camera that does not already exist on this class is
        added as a delegating property. Setters of properties in
        :attr:`disarmed_properties` are wrapped with :func:`disarmer`.
        """

        # to get around late binding
        def prop_factory(thor_prop, disarmed=False, notified=False):

            def fget(self):
                return thor_prop.fget(self._camera)

            def fset(self, val):
                # with self.acquisition_lock: # this leads to infinite locking as raw_snapshot can set frames_per_trigger
                # it should be possible to simply lock
                return thor_prop.fset(self._camera, val)

            # fget = waiter(fget)
            # fset = waiter(fset)
            if disarmed:
                fset = disarmer(fset)
            # if notified: sreturn NotifiedProperty(fget, fset)
            ## ^ for some reason this makes acquisition lock unstable
            ##  It's a bit disappointing but I don't know how to fix - ee306
            return property(fget, fset)

        cls = self.__class__
        for thor_attr in dir(thor_cls := self._camera.__class__):
            if hasattr(thor_prop := getattr(thor_cls, thor_attr), 'fget'):
                # if it's a property
                if not hasattr(cls, thor_attr):
                    # and it's not in Kiralux already
                    setattr(
                        cls,
                        thor_attr,  # add the property
                        prop_factory(thor_prop, thor_attr in cls.disarmed_properties, thor_attr
                                     in cls.notified_properties))
                    # if it's in disarmed_properties,
                    # decorate the setter and return a
                    # notified property appropriately.

    @property
    def exposure(self):
        """Exposure time in milliseconds (pyopenlab convention; SDK reports microseconds)."""
        return self.exposure_time_us / 1000.0

    @exposure.setter
    def exposure(self, val):
        self.exposure_time_us = int(val * 1000)

    def get_frame(self):
        """Block until a frame is available and return it.

        Returns:
            The pending frame from the camera; polls every 0.1 s until one arrives.
        """
        while (f := self._camera.get_pending_frame_or_null()) is None:
            # pass
            time.sleep(0.1)
        return f

    def process_color_frame(self, frame, square_image=False):
        """Demosaic a raw Bayer frame into an RGB image.

        Args:
            frame: A frame object exposing an ``image_buffer``.
            square_image (bool): Unused; cropping to square is handled separately via
                :meth:`make_square`.

        Returns:
            numpy.ndarray: An ``(H, W, 3)`` RGB image, flipped vertically and horizontally.
        """
        color_image_data = self._mono_to_color_processor.transform_to_24(
            frame.image_buffer, self._image_width, self._image_height)
        color_image_data = color_image_data.reshape(self._image_height, self._image_width, 3)
        # return color_image_data
        return color_image_data[::-1, ::-1, :]

    def make_square(self, color_image_data):
        """Crop a wide image symmetrically to a square based on the sensor dimensions.

        Args:
            color_image_data (numpy.ndarray): The image to crop.

        Returns:
            numpy.ndarray: The horizontally cropped, square image.
        """
        dif = (self._image_width - self._image_height) // 2
        return color_image_data[:, dif:self._image_width - dif, :]

    def raw_snapshot(self):
        """Capture and process a single frame.

        Issues a software trigger first unless live view is already running.

        Returns:
            tuple: ``(True, image)`` on success, or ``(False, None)`` if no frame.
        """
        if not self.live_view:
            self._camera.issue_software_trigger()
        # if it's in live_view, camera should already be triggered
        with self.acquisition_lock:
            frame = self.get_frame()

        if frame:
            return True, self.process_frame(frame)

        return False, None

    @Camera.live_view.setter
    def live_view(self, live_view):
        """Start or stop continuous acquisition.

        Toggles the camera between unlimited frames-per-trigger (live) and single-frame
        snapshot mode. Setting frames-per-trigger disarms and re-arms via :func:`disarmer`.

        Args:
            live_view (bool): ``True`` to begin live acquisition, ``False`` to stop it.
        """
        if live_view == self._live_view:
            return  # small redundancy with Camera.live_view
        Camera.live_view.fset(self, live_view)
        if live_view:
            self.frames_per_trigger_zero_for_unlimited = 0  # unlimited
            # decorator should trigger as self.live_view == True
        else:
            self.frames_per_trigger_zero_for_unlimited = 1  # disarms and rearms

    # def color_image(self, **kwargs):

    def get_control_widget(self):
        "Get a Qt widget with the camera's controls (but no image display)"
        return KiraluxCameraControlWidget(self)


class KiraluxCameraControlWidget(CameraControlWidget):
    """A control widget for the Thorlabs camera, with extra buttons."""

    def __init__(self, camera):
        super().__init__(camera, auto_connect=False)
        gb = QuickControlBox()
        gb.add_doublespinbox("exposure", *(e / 1000 for e in camera.exposure_time_range_us))
        gb.add_spinbox("gain", *camera.gain_range)  # setting range
        gb.add_button("show_camera_properties_dialog", title="Camera Setup")
        gb.add_button("show_video_format_dialog", title="Video Format")
        self.layout().insertWidget(1, gb)  # put the extra settings in the middle
        self.quick_settings_groupbox = gb
        self.auto_connect_by_name(controlled_object=self.camera)


if __name__ == '__main__':

    k = Kiralux()
    k.show_gui(False)
    k.exposure = 100
    k.gain = 10

    # %%


    def setter():
        k.gain = 100
        k.exposure = 50
        print('broke')

    def poller():
        for _ in range(10):
            k.raw_image()
        print('polled')

    def work():
        t = threading.Thread(target=setter)
        t2 = threading.Thread(target=poller)
        t2.start()
        t.start()

    # work()
