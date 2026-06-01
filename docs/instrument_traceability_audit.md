# Instrument Hardware Traceability Audit

This report audits the `pyopenlab/instrument/` tree for files whose name or top-level
docstring does not clearly identify the hardware they control.  Files already named after
a specific manufacturer/model (e.g. `thorlabs_sc10.py`, `keithley_2635a_smu.py`) and
abstract base classes are excluded from this audit.

**Next step:** review the tables below, fill in any open questions in Group B, then use
this document to guide docstring additions or renames in a follow-up pass.

---

## Group A — Hardware identified; docstring recommended

Hardware was identified from the source code (imports, USB VIDs, DLL names, class names,
or command protocols) but is not stated in the filename or any docstring.
The recommended fix is to add the suggested one-line docstring as the module docstring.

| File (relative to `pyopenlab/instrument/`) | Hardware identified | Protocol | Suggested module docstring |
|---------------------------------------------|---------------------|----------|----------------------------|
| `electronics/aom.py` | Agilent / Keysight USB instrument — VID `0x0957`, PID `0x0407` (power supply / AOM driver) | VISA over USB | `"""Driver for an Agilent/Keysight USB instrument (VID 0x0957, PID 0x0407) used to control an AOM via SCPI over VISA."""` |
| `filters/superchrome.py` | Fianium SuperChrome tunable spectral filter | Windows DLL (`SuperChromeSDK.dll`) | `"""Driver for the Fianium SuperChrome tunable spectral filter. Communicates via the SuperChromeSDK.dll Windows library."""` |
| `light_sources/OPO.py` | Inspire OPO — likely iXBlue / Newport Inspire series (`inspire_OPO` class) | RS-232 serial, 9600 baud | `"""Driver for the Inspire OPO (iXBlue/Newport Inspire series). Communicates via RS-232 at 9600 baud."""` |
| `camera/uc480.py` | IDS Imaging uEye uc480 camera | `instrumental` Python SDK | `"""Driver for IDS Imaging uEye uc480 cameras via the `instrumental` library."""` |
| `electronics/nidaq.py` | National Instruments DAQ hardware (NI-DAQmx) | NI-DAQmx / PyDAQmx | `"""Driver for National Instruments DAQ hardware. Requires NI-DAQmx drivers and the PyDAQmx Python wrapper."""` |
| `electronics/FrequencyCounter.py` | Frequency Counter F390 (manufacturer TBC — class is `Frequency_counter_F390`) | Serial, 115200 baud, XON/XOFF | `"""Driver for the F390 frequency counter. Communicates via serial at 115200 baud with XON/XOFF flow control."""` |
| `electronics/TGF4242_Function_Generator.py` | Thurlby Thandar Instruments (TTi) TGF4242 dual-channel function generator | Serial (SCPI-like) | `"""Driver for the TTi TGF4242 dual-channel function generator. Communicates via serial."""` |
| `electronics/gio_rotator.py` | Arduino-based rotation stage (custom build, `ArduinoRotator` class) | RS-232 serial, S/M command protocol | `"""Driver for an Arduino-based rotation stage. Communicates via serial using S/M prefixed commands."""` |
| `stage/rotation_stage.py` | Stepper-motor rotation stage — generic hex-command serial protocol | Serial (hex commands) | `"""Backend driver for a stepper-motor rotation stage that uses a hex-encoded serial command protocol."""` |
| `filters/aotf.py` | Acousto-optic tunable filter (AOTF) driven by a serial microcontroller | Serial, 38400 baud | `"""Driver for an acousto-optic tunable filter (AOTF) with a serial microcontroller interface at 38400 baud."""` |
| `filters/varispec.py` | VariSpec liquid-crystal tunable filter (Cambridge Research Instruments / Andover) | Serial, 9600 baud | `"""Driver for a VariSpec liquid-crystal tunable filter (CRI/Andover). Communicates via serial at 9600 baud."""` |

---

## Group B — Custom / lab-specific hardware (open questions)

These files target hardware unique to a specific lab or researcher.  Please fill in the
**Your answer** column so a docstring can be written accurately.

| File | Evidence found in code | Open question | Your answer |
|------|------------------------|---------------|-------------|
| `electronics/gamari_fpga.py` | Class `Timetagger`; imports `timetag.capture_pipeline`; spawns `timetag-cat` subprocess | What is the "Gamari FPGA"? Is there a public project page, paper, or GitHub repo that describes this hardware? | |
| `shutter/southampton_custom.py` | Class `ILShutter`; 19200 baud, 7-bit odd parity; SCPI-like `ct`/`S4U`/`S4D` commands | What does "Intelligent Light Southampton" refer to — a commercially sold shutter, a custom-built unit, or a collaboration instrument? | |
| `electronics/SLM/__init__.py` | Pattern generators, Zernike polynomials, GUI framework; no manufacturer string visible | Which spatial light modulator (SLM) manufacturer and model does this target? | |

---

## Group C — Intentionally hardware-agnostic (utilities and wrappers)

These files are **not** drivers for a specific instrument.  They are generic utilities or
wrappers that combine or abstract over other drivers.  No hardware traceability fix is
needed; they may benefit from a brief docstring clarifying their role instead.

| File | What it is |
|------|------------|
| `electronics/Talk2Computer.py` | UDP socket sender — network communication utility (no physical instrument) |
| `electronics/receiver.py` | UDP socket receiver — network communication utility (no physical instrument) |
| `electronics/power_control.py` | Generic power control wrapper: combines an AOM/stage actuator with a power meter for closed-loop calibration |
| `stage/wheel_of_power.py` | Generic wrapper: combines a rotation stage with a power meter for power-vs-angle calibration |
| `controller/static_tuner.py` | Generic feedback controller framework: wires an arbitrary sensor to an arbitrary actuator |
| `camera/opencv.py` | Generic OpenCV camera wrapper: supports any camera accessible via `cv2.VideoCapture` |
| `spectrometer/spectrometer_aligner.py` | Generic spectrometer alignment utility: works with any spectrometer + stage backend |
| `stage/rotators.py` | GUI wrapper for arbitrary rotator backends; not tied to specific hardware |
