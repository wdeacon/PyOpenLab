# -*- coding: utf-8 -*-
"""Camera driver for the Photometrics Prime BSI, built on the ``pyvcam`` PVCAM bindings."""

from functools import wraps

import numpy as np
from pyvcam import pvc
from pyvcam.camera import Camera as VCamera

from pyopenlab.instrument.camera import Camera
from pyopenlab.instrument.camera import CameraControlWidget
from pyopenlab.ui.ui_tools import QuickControlBox
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
from pyopenlab.utils.notified_property import NotifiedProperty
from pyopenlab.utils.thread_utils import background_action
from pyopenlab.utils.thread_utils import locked_action

try:
    pvc.uninit_pvcam()
except RuntimeError:
    pass


def disarmer(f):
    """Decorate a setter so live view is paused while it runs and resumed afterwards.

    Args:
        f: The function (typically a property setter) to wrap.

    Returns:
        The wrapped function which toggles ``live_view`` off before the call and back
        on afterwards if it was originally on.
    """

    @wraps(f)
    def inner_func(self, *args, **kwargs):
        if (l := self.live_view):
            self.live_view = False
        out = f(self, *args, **kwargs)

        if l:
            self.live_view = True
        return out

    return inner_func


class PrimeBSI(Camera):
    """Photometrics Prime BSI scientific CMOS camera.

    Wraps a ``pyvcam`` :class:`Camera` instance, mirroring its properties onto this class
    so they are accessible directly (see :meth:`_populate_properties`).

    Attributes:
        notified_properties: Property names surfaced in the GUI as notified properties.
        disarmed_properties: Property names whose setters require live view to be paused.
        metadata_property_names: Property names included in captured metadata.
        pixel_max: Maximum pixel value the sensor reports.
    """

    notified_properties = ('gain',)  # properties that are in the gui
    disarmed_properties = ('gain', 'exp_time')  # properties that break live view if changed
    metadata_property_names = ('exposure', 'gain')
    pixel_max = 2047.

    def __init__(self):
        super().__init__()
        pvc.init_pvcam()
        self._camera = next(VCamera.detect_camera())
        if not self._camera.is_open:
            self._camera.open()
        self._populate_properties()

    def _populate_properties(self):
        """Copy the underlying pyvcam camera's properties onto this class.

        Each property of the wrapped camera that does not already exist on this class is
        added as a property that delegates to the camera instance. Properties named in
        :attr:`disarmed_properties` get their setters wrapped with :func:`disarmer`, and
        those in :attr:`notified_properties` become :class:`NotifiedProperty` instances.
        """

        def prop_factory(prime_prop, notified=False, disarmed=False):  # to get around late binding

            def fget(self):
                return prime_prop.fget(self._camera)

            def fset(self, val):
                return prime_prop.fset(self._camera, val)

            if disarmed:
                fset = disarmer(fset)
            if notified:
                return NotifiedProperty(*map(locked_action, (fget, fset)))
            return property(*map(locked_action, (fget, fset)))

        cls = self.__class__
        for prime_attr in dir(prime_cls := self._camera.__class__):
            if hasattr(prime_prop := getattr(prime_cls, prime_attr), 'fget'):
                # if it's a property
                if not hasattr(cls, prime_attr):
                    # and it's not in Kiralux already
                    setattr(
                        cls,
                        prime_attr,  # add the property
                        prop_factory(prime_prop, prime_attr in cls.notified_properties, prime_attr
                                     in cls.disarmed_properties))
                    # if it's in disarmed_properties,
                    # decorate the setter and return a
                    # notified property appropriately.
    @NotifiedProperty
    def exposure(self):
        """Exposure time in milliseconds (converted from microseconds when needed)."""
        if self.exp_res_index:  # us
            return self.exp_time // 1_000
        return self.exp_time

    @exposure.setter
    def exposure(self, val):  # ms
        if self.exp_res_index:  # us
            val *= 1_000
        self.exp_time = int(val)

    def raw_snapshot(self):
        """Capture a single frame from the camera.

        Returns:
            tuple: ``(True, frame)`` where ``frame`` is the pixel data, polled from the
            live stream if live view is active, otherwise grabbed directly.
        """
        if self.live_view:
            frame = self._camera.poll_frame()[0]['pixel_data']
        else:
            frame = self._camera.get_frame()
        return True, frame

    @Camera.live_view.setter
    def live_view(self, live_view):
        """Start or stop continuous acquisition.

        Args:
            live_view (bool): ``True`` to begin live acquisition, ``False`` to stop it.
        """
        if live_view == self._live_view:
            return  # small redundancy with Camera.live_view
        Camera.live_view.fset(self, live_view)
        if live_view:
            self._camera.start_live()
        else:
            self._camera.finish()

    def color_image(self, **kwargs):
        """Return a captured frame placed in the red channel of an otherwise zero RGB image.

        Args:
            **kwargs: Forwarded to :meth:`raw_image`.

        Returns:
            numpy.ndarray: An ``(H, W, 3)`` array with the frame in channel 0.
        """
        r = self.raw_image(**kwargs)
        return np.append(r[:, :, None], np.zeros(r.shape + (2,)), axis=-1)

    def stack(self, exposures=(10, 100, 1000), **kwargs):
        """Capture a stack of images, one per requested exposure time.

        Live view is disabled for the duration and restored afterwards.

        Args:
            exposures: Iterable of exposure times (ms) to capture in turn.
            **kwargs: Forwarded to :meth:`raw_image`.

        Returns:
            ArrayWithAttrs: Array of shape ``(len(exposures), *frame_shape)`` carrying an
            ``exposures`` attribute listing the exposure times used.
        """
        live_view = self.live_view
        self.live_view = False
        for i, e in enumerate(exposures):
            self.exposure = e
            im = self.raw_image(**kwargs)
            if not i:
                if isinstance(im, ArrayWithAttrs):
                    images = ArrayWithAttrs(np.empty(
                        (len(exposures),) + im.shape,
                        dtype=im.dtype,
                    ),
                                            attrs=im.attrs | {'exposures': list(exposures)})
                else:
                    images = ArrayWithAttrs(np.empty((len(exposures),) + im.shape, dtype=im.dtype),
                                            attrs={'exposures': list(exposures)})
            images[i] = im
        self.live_view = live_view
        return images

    @classmethod
    def combine(cls, stack):
        """Combine an exposure stack into a single HDR-style image.

        Near-saturated pixels are masked out, then each frame is normalised by its
        exposure time and the frames are averaged (ignoring the masked values).

        Args:
            stack (ArrayWithAttrs): Output of :meth:`stack`, carrying an ``exposures``
                attribute.

        Returns:
            numpy.ndarray: The exposure-normalised, averaged image.

        Note:
            ``cls.pixel_max`` is a scalar (``2047.``) but this method subscripts it as
            ``cls.pixel_max[1]``, which raises ``TypeError`` at runtime. Left unchanged
            pending clarification of the intended saturation threshold.
        """
        exposures = stack.attrs['exposures']
        stack[stack >= cls.pixel_max[1] * 0.9] = np.nan

        weighted = np.divide(stack, exposures[:, None, None])
        combined = np.nanmean(weighted, axis=0)
        return combined

    def get_control_widget(self):
        "Get a Qt widget with the camera's controls (but no image display)"
        return PrimeCameraControlWidget(self)


class PrimeCameraControlWidget(CameraControlWidget):
    """A control widget for the Prime BSI camera, with extra buttons."""

    def __init__(self, camera):
        super().__init__(camera, auto_connect=False)
        gb = QuickControlBox()
        gb.add_spinbox("exposure", 0, 10_000)
        gb.add_spinbox("gain", 1, 3)  # setting range
        gb.add_button("show_camera_properties_dialog", title="Camera Setup")
        gb.add_button("show_video_format_dialog", title="Video Format")
        self.layout().insertWidget(1, gb)  # put the extra settings in the middle
        self.quick_settings_groupbox = gb
        self.auto_connect_by_name(controlled_object=self.camera)


if __name__ == '__main__':
    p = PrimeBSI()
    p.show_gui(False)
