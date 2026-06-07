# -*- coding: utf-8 -*-
"""OpenCV-backed :class:`Camera` implementation.

Wraps an OpenCV ``VideoCapture`` device so that any camera OpenCV can open (webcams, USB cameras,
etc.) can be driven through the pyopenlab Camera interface.
"""
import sys

try:
    import cv2
except ImportError:
    explanation = """
WARNING: could not import the Open CV library.
    
Make sure you have installed OpenCV, and that its version matches your Python 
architecture (64 or 32 bit).  You can download a simple installer from:
http://www.lfd.uci.edu/~gohlke/pythonlibs/#opencv
We are using Python %d.%d, so get the corresponding package.
""" % (sys.version_info.major, sys.version_info.minor)
    try:
        import traitsui
        import traitsui.message
        traitsui.message.error(explanation, "OpenCV Missing", buttons=["OK"])
    except Exception as e:
        print("uh oh, problem with the message...")
        print(e)
        pass
    finally:
        raise ImportError(explanation)

from pyopenlab.instrument.camera import Camera
from pyopenlab.instrument.camera import CameraParameter


class OpenCVCamera(Camera):
    """A :class:`Camera` driven by an OpenCV ``VideoCapture`` device.

    Args:
        capturedevice: Index or identifier of the capture device to open, passed straight to
            ``cv2.VideoCapture``.
    """

    def __init__(self, capturedevice=0):
        self.cap = cv2.VideoCapture(capturedevice)

        super(OpenCVCamera, self).__init__()  #NB this comes after setting up the hardware

    def close(self):
        """Stop communication with the camera and allow it to be re-used."""
        super(OpenCVCamera, self).close()
        self.cap.release()

    def raw_snapshot(self, suppress_errors=False):
        """Take a snapshot and return it, bypassing filters.

        Tries up to 10 times to read a frame; colour frames are converted from OpenCV's BGR order to
        RGB.

        Args:
            suppress_errors: If True, return ``(False, None)`` instead of raising when no frame can
                be captured.

        Returns:
            tuple[bool, numpy.ndarray | None]: ``(True, frame)`` on success, or ``(False, None)`` if
            capture failed and ``suppress_errors`` is True.

        Raises:
            IOError: If no frame could be captured and ``suppress_errors`` is False.
        """
        with self.acquisition_lock:
            for i in range(10):
                try:
                    ret, frame = self.cap.read()
                    assert ret, "OpenCV's capture.read() returned False :("
                    if len(frame.shape) == 3:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    return ret, frame
                except Exception as e:
                    print("Attempt number {0} failed to capture a frame from the camera!".format(i))
                    print(e)
        print("Camera.raw_snapshot() has failed to capture a frame.")
        if not suppress_errors:
            raise IOError("Dropped too many frames from camera :(")
        else:
            return False, None

    def get_camera_parameter(self, parameter_name):
        """Get the value of a camera parameter (prefer the corresponding property).

        Args:
            parameter_name: Name of a ``cv2`` capture property constant, e.g. ``'CAP_PROP_FPS'``.

        Returns:
            The current value of the parameter, as returned by ``VideoCapture.get``.
        """
        return self.cap.get(getattr(cv2, parameter_name))

    def set_camera_parameter(self, parameter_name, value):
        """Set the value of a camera parameter (prefer the corresponding property).

        Args:
            parameter_name: Name of a ``cv2`` capture property constant, e.g. ``'CAP_PROP_FPS'``.
            value: The value to set.

        Returns:
            bool: Whether ``VideoCapture.set`` accepted the value.
        """
        return self.cap.set(getattr(cv2, parameter_name), value)


# Add properties to change the camera parameters, based on OpenCV's parameters.
# It may be wise not to do this, and to filter them instead...
for cvname in dir(cv2):
    if cvname.startswith("CAP_PROP_"):
        name = cvname.replace("CAP_PROP_", "").lower()
        setattr(OpenCVCamera, name, CameraParameter(cvname, doc="the camera property %s" % name))

if __name__ == '__main__':
    cam = OpenCVCamera()
    cam.show_gui()
