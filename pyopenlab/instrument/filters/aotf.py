"""Driver and Qt UI for an acousto-optic tunable filter (AOTF).

The :class:`AOTF` class talks to the AOTF controller over a serial port using its
text command protocol (``dds``/``dau``/``cal`` commands). Channels can be tuned by
wavelength or drive frequency and given an amplitude (RF power). :class:`AOTF_UI`
provides a Qt widget exposing per-channel wavelength/power controls.
"""

import time

import numpy as np

import pyopenlab.instrument.serial_instrument as serial
from pyopenlab.ui.ui_tools import *
from pyopenlab.utils.gui import *


class AOTF(serial.SerialInstrument):
    """Serial driver for an acousto-optic tunable filter controller.

    Attributes:
        termination_character (str): Line terminator appended to outgoing commands.
        termination_line (str): Terminator expected on incoming responses.
        port_settings (dict): Pyserial port configuration for the controller.
    """

    termination_character = "\n"
    termination_line = "\r"

    port_settings = dict(
        baudrate=38400,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,  #wait at most one second for a response
        writeTimeout=1,  #similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=False)

    def __init__(self, port=None):
        """Open the serial port, enable daughter-board control, and load calibration.

        Args:
            port (str, optional): Serial port name. If None, the base class attempts to
                auto-detect or prompt for a port.
        """

        #Open communication port
        super(AOTF, self).__init__(port=port)

        # "dau en" enables the microcontroller to manipulate the Daughter Board controls.
        r = self.query("dau en")
        print("Daughter Board control enable, response:", r)

        self.set_default_calibration()

        # self.aotf_off()
        self.query("dau dac * 16383")

        # Macro AOTF_setup()
        # VDT2/P=COM3 baud=38400, stopbits=1, databits=8, parity=0, echo=0
        # Variable/G AOTFint0=0,AOTFint1=0,AOTFint2=0,AOTFwl0=670,AOTFwl1=570,AOTFwl2=550
        # AOTF_ModMax()
        # AOTF_off()

    def set_amplitude(self, channel, amplitude):
        """Set the RF drive amplitude (power) for a channel.

        Args:
            channel (int): Channel index, in the range 0-7.
            amplitude (int): Drive amplitude, in the range 0-16383.

        Raises:
            AssertionError: If channel or amplitude is outside its valid range.
        """
        assert (int(channel) >= 0 and int(channel) <= 7), "Channel index in range 0-7"
        assert (int(amplitude) >= 0 and
                int(amplitude) <= 16383), "Channel amplitude in range 0-16383"
        command = "dds a {0} {1}".format(channel, amplitude)
        response = self.query(command)
        print("AOTF.set_amplitude:", response)
        return

    def set_wavelength(self, channel, wavelength):
        """Set the optical wavelength for a channel.

        Args:
            channel (int): Channel index, in the range 0-7.
            wavelength (float): Target wavelength in nm. The assertion accepts
                450.0-1100.0; note the device firmware itself clamps to roughly
                450-690 nm.

        Raises:
            AssertionError: If channel or wavelength is outside its valid range.
        """
        assert (int(channel) >= 0 and int(channel) <= 7), "Channel index in range 0-7"
        assert (float(wavelength) >= 450.0 and
                float(wavelength) <= 1100.0), "Channel wavelength in range 450.0-690.0"
        command = "dds w {0} {1:.1f}".format(
            channel, wavelength)  #Notation: :.1f - show 'wavelength' to 1 float ('f') point places
        response = self.query(command)
        print("AOTF.set_wavelength:", response)
        return

    def set_frequency(self, channel, frequency):
        """Set the RF drive frequency for a channel.

        Args:
            channel (int): Channel index, in the range 0-7.
            frequency (float): Drive frequency (assumed to be in MHz).

        Raises:
            AssertionError: If channel is outside the range 0-7.
        """
        #Note: frequency in MHz?
        assert (int(channel) >= 0 and int(channel) <= 7), "Channel index in range 0-7"
        command = "dds f {0} {1:6f}".format(
            int(channel),
            frequency)  #Notation: :.6f - show 'frequency' to 6 float ('f') point places
        response = self.query(command)
        print("AOTF.set_frequency:", response)

    def set_default_calibration(self):
        """Write the default wavelength-tuning polynomial coefficients and save them.

        Sends the ``cal tuning`` coefficients (orders 0-3) followed by ``cal save`` so the
        controller persists the calibration.

        Note:
            A historical comment warns that loading this calibration once caused the AOTF
            to stop responding; the dead alternate calibration block has been removed but
            the behaviour is unverified on current hardware.
        """

        r = self.query("cal tuning 0 397.46")
        print("Calibration step1:", r)
        r = self.query("cal tuning 1 -1.2232")
        print("Calibration step2:", r)
        r = self.query("cal tuning 2 1.4658e-3")
        print("Calibration step3:", r)
        r = self.query("cal tuning 3 -6.15e-7")
        print("Calibration step4:", r)
        r = self.query("cal save")
        print("Calibration step5:", r)

        return

    def aotf_off(self):
        """Set every channel amplitude to zero, turning the filter output off."""
        for c in range(0, 8):
            self.set_amplitude(channel=c, amplitude=0)
        return

    def enable_channel_by_frequency(self, channel, frequency, amplitude):
        """Tune a channel by frequency and set its amplitude.

        Args:
            channel (int): Channel index, in the range 0-7.
            frequency (float): Drive frequency (assumed MHz).
            amplitude (int): Drive amplitude, in the range 0-16383.
        """
        self.set_frequency(channel, frequency)
        self.set_amplitude(channel, amplitude)

    def enable_channel_by_wavelength(self, channel, wavelength, amplitude):
        """Tune a channel by wavelength and set its amplitude.

        Args:
            channel (int): Channel index, in the range 0-7.
            wavelength (float): Target wavelength in nm.
            amplitude (int): Drive amplitude, in the range 0-16383.
        """
        self.set_wavelength(channel, wavelength)
        self.set_amplitude(channel, amplitude)

    def disable_channel(self, channel):
        """Turn a channel off by setting its amplitude to zero.

        Args:
            channel (int): Channel index, in the range 0-7.
        """
        self.set_amplitude(channel, 0)


class AOTF_UI(QtWidgets.QWidget, UiTools):
    """Qt widget exposing per-channel wavelength and power controls for an AOTF."""

    def __init__(self, device, parent=None, debug=False, verbose=False):
        """Build the UI from ``aotf.ui`` and wire up the channel controls.

        Args:
            device (AOTF): The AOTF instrument this widget controls.
            parent (QWidget, optional): Parent Qt widget.
            debug (bool): Unused flag retained for API compatibility.
            verbose (bool): Unused flag retained for API compatibility.

        Raises:
            ValueError: If ``device`` is not an :class:`AOTF` instance.
        """
        if not isinstance(device, AOTF):
            raise ValueError("Object is not an instance of the AOTF Class")
        super(AOTF_UI, self).__init__()

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'aotf.ui'), self)

        #aotf:
        self.aotf = device

        self.wavelength_textboxes = [
            self.chn1_wl, self.chn2_wl, self.chn3_wl, self.chn4_wl, self.chn5_wl, self.chn6_wl,
            self.chn7_wl, self.chn8_wl]
        self.power_textboxes = [
            self.chn1_pwr, self.chn2_pwr, self.chn3_pwr, self.chn4_pwr, self.chn5_pwr,
            self.chn6_pwr, self.chn7_pwr, self.chn8_pwr]
        self.active = [
            self.chn1_toggle, self.chn2_toggle, self.chn3_toggle, self.chn4_toggle,
            self.chn5_toggle, self.chn6_toggle, self.chn7_toggle, self.chn8_toggle]

        for wl in self.wavelength_textboxes:
            wl.textChanged.connect(self.set_wavelength)

        for pwr in self.power_textboxes:
            pwr.textChanged.connect(self.set_power)

        self.off_btn.clicked.connect(self.set_off)
        self.on_btn.clicked.connect(self.set_on)
        self.settings = [[0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]

        self.set_wavelength()
        self.set_power()

    def set_wavelength(self):
        """Read each wavelength textbox and cache the values into ``self.settings``."""
        try:
            for i in range(len(self.wavelength_textboxes)):
                wavelength = float(self.wavelength_textboxes[i].text())
                self.settings[i][0] = wavelength
            print(self.settings)
        except ValueError as e:
            print(e)

        return

    def set_power(self):
        """Read each power textbox and cache the values into ``self.settings``."""
        try:
            for i in range(len(self.power_textboxes)):
                power = int(self.power_textboxes[i].text())
                self.settings[i][1] = power
        except ValueError as e:
            print(e)
        return

    def set_on(self):
        """Apply cached settings to every checked channel and disable the rest.

        Note:
            This method references the module-level ``aotf`` global rather than
            ``self.aotf``; it will raise ``NameError`` unless that global has been
            populated (e.g. via :func:`make_gui`). It should use ``self.aotf``.
        """
        print(self.settings)
        channel_is_on = [bool(a.isChecked()) for a in self.active]
        print(channel_is_on)
        for i, is_on in enumerate(channel_is_on):
            if is_on == True:
                wl = self.settings[i][0]
                pwr = self.settings[i][1]
                print("wavelength:", wl)
                aotf.enable_channel_by_wavelength(i, wl, pwr)
            else:
                aotf.disable_channel(i)
        return

    def set_off(self):
        """Turn the AOTF fully off via :meth:`AOTF.aotf_off`."""
        self.aotf.aotf_off()
        return


def make_gui():
    """Open an AOTF on a hard-coded serial port and launch the Qt UI."""
    global aotf
    aotf = AOTF("/dev/ttyUSB2")
    app = get_qt_app()
    ui = AOTF_UI(device=aotf, debug=False)
    ui.show()
    sys.exit(app.exec_())


def flash_wavelengths(wavelengths, t_sec):
    """Repeatedly flash a set of wavelengths on and off (runs forever).

    Args:
        wavelengths (Sequence[float]): Wavelengths in nm, one per channel index.
        t_sec (float): On and off dwell time, in seconds.
    """
    aotf = AOTF("/dev/ttyUSB2")
    while True:
        for i in range(len(wavelengths)):
            aotf.enable_channel_by_wavelength(i, wavelengths[i], 8000)
        time.sleep(t_sec)
        for i in range(len(wavelengths)):
            aotf.disable_channel(i)
        time.sleep(t_sec)
    return


def say(text):
    """Speak ``text`` aloud using the ``pyttsx`` text-to-speech engine.

    Args:
        text (str): The text to speak.
    """
    import pyttsx
    engine = pyttsx.init()
    engine.say(text)
    engine.runAndWait()
    return


def flash_frequency(f):
    """Repeatedly flash channel 1 at frequency ``f`` on and off (runs forever).

    Args:
        f (float): Drive frequency (assumed MHz).
    """
    aotf = AOTF("/dev/ttyUSB2")
    while True:
        aotf.enable_channel_by_frequency(1, f, 8000)
        time.sleep(0.4)
        aotf.disable_channel(1)
        time.sleep(0.4)


def set_frequency(fs):
    """Enable one channel per frequency in ``fs``, indexed by position.

    Args:
        fs (Sequence[float]): Drive frequencies (assumed MHz); ``fs[i]`` is applied to
            channel ``i``.
    """

    aotf = AOTF("/dev/ttyUSB2")
    for i, f in enumerate(fs):
        # aotf.disable_channel(i)
        aotf.enable_channel_by_frequency(i, f, 8000)


def scan_frequency(freqs, t):
    """Step channel 1 through ``freqs``, announcing each value and dwelling at it.

    Args:
        freqs (Iterable[float]): Drive frequencies (assumed MHz) to scan through.
        t (float): On and off dwell time at each frequency, in seconds.
    """
    aotf = AOTF("/dev/ttyUSB2")
    for f in freqs:
        print("freq:", f)
        aotf.enable_channel_by_frequency(1, f, 8000)
        say("{0:.3g} megahertz".format(f))
        say("measure")
        time.sleep(t)

        aotf.disable_channel(1)
        time.sleep(t)

    return


if __name__ == "__main__":
    # time.sleep(10)

    set_frequency([85])
    # for f in range(60,86):
    # set_frequency(f)
    # time.sleep(1)
    # say("{0:.3g} megahertz".format(f))
    # scan_frequency(range(48,86),1)
    # scan_frequency(range(86,95),1)
    # make_gui()
    # flash_wavelengths([690],1)
