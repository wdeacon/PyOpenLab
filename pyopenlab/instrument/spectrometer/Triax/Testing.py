"""Manual setup script for a Lab 5 Trandor experiment.

Run directly to bring up the camera-with-location GUI, an Ocean Optics spectrometer, the
spectrometer aligner, a white-light shutter and a :class:`Trandor`, then configure the Triax
grating and slit. Intended for interactive use, not import.
"""

from pyopenlab.instrument.camera.camera_with_location import CameraWithLocation
from pyopenlab.instrument.camera.lumenera import LumeneraCamera
from pyopenlab.instrument.shutter.BX51_uniblitz import Uniblitz
from pyopenlab.instrument.spectrometer.seabreeze import OceanOpticsSpectrometer
from pyopenlab.instrument.spectrometer.spectrometer_aligner import SpectrometerAligner
from pyopenlab.instrument.spectrometer.Triax.Trandor_Lab5 import Trandor
from pyopenlab.instrument.stage.prior import ProScan

cam = LumeneraCamera(1)
stage = ProScan("COM1", hardware_version=2)
CWL = CameraWithLocation(cam, stage)
CWL.show_gui(blocking=False)

spectrometer = OceanOpticsSpectrometer(0)
spectrometer.show_gui(blocking=False)

#aligner
aligner = SpectrometerAligner(spectrometer, stage)

# Display white light shutter control

whiteShutter = Uniblitz("COM8")
whiteShutter.show_gui(blocking=False)
#
trandor = Trandor(whiteShutter)
Trandor.HSSpeed = 2
trandor.Grating(1)
trandor.triax.Slit(100)

#trandor.SetParameter('SetTemperature',-90)
#trandor.CoolerON()
andor_gui = trandor.get_qt_ui()
andor_gui.show()
