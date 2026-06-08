"""Driver and Qt UI for the ADLINK PCI-9812 high-speed analog input card.

The card is driven through the ADLINK PCIS-DASK DLL via ctypes. Captured voltage
traces are used for dynamic light scattering (photon-counting / autocorrelation)
post-processing.

Note:
    ``Adlink9812.get_card_sample_rate`` calls ``DLL.GetActualRate(...)`` where ``DLL``
    is undefined (it should be ``self.dll``); the method raises ``NameError``. Several
    methods also use bare ``except:`` clauses, which swallow all exceptions.
"""

import ctypes
from ctypes import *
import datetime
import logging
import math
import os
import sys
import threading
import timeit

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import scipy.stats

import pyopenlab
from pyopenlab.experiment.dynamic_light_scattering import dls_signal_postprocessing
from pyopenlab.instrument import Instrument
from pyopenlab.instrument.electronics import adlink9812_constants
from pyopenlab.ui.ui_tools import *
from pyopenlab.utils.gui import *

### Steps of PCI-DASK applications:
#
# Full documentation: ADLINK PCIS-DASK User's Manual
# Function reference: http://www.adlinktech.com/publications/manual/Software/PCIS-DASK-X/PSDASKFR.pdf

#	1. Register card
#	2. Configuration function
#	3. AI/AO/DI/DO Operation function
#		AI: analog input
#			non-buffered single-point AI: poll device for data
#			buffered: interrupt transfer/DMA (direct memory access) to transfer data from device to user buffer
#		AO: analog output
#		DI: digital input
#		DO: digital output
#		3.1 ---- Configuration ---
#			Must configure your card (our case: AI_9812_Config, passing card_id (from registration and parameters for registering))
#	4. Release card

DATATYPE = c_ushort
VERSION = 0.01


class Adlink9812(Instrument):
    """Instrument wrapper for the ADLINK PCI-9812 analog input card.

    Loads the PCIS-DASK DLL, registers and configures the card, and provides
    synchronous and asynchronous double-buffered analog input reads.

    Note:
        ``get_card_sample_rate`` references an undefined ``DLL`` global and raises
        ``NameError``.
    """

    def __init__(self,
                 dll_path="C:\ADLINK\PCIS-DASK\Lib\PCI-Dask64.dll",
                 verbose=False,
                 debug=False):
        """Load the PCIS-DASK DLL, then register and configure the card.

        Args:
            dll_path: Path to the PCIS-DASK DLL.
            verbose: Unused; retained for call compatibility.
            debug: If True, skip hardware access and generate synthetic data instead.

        Raises:
            ValueError: ``dll_path`` does not exist and debug mode is not enabled.
        """
        super(Adlink9812, self).__init__()
        self.debug = debug
        if self.debug:
            self.log(message="Instrument.Adlink9812: DEBUG MODE")
        if not os.path.exists(dll_path):
            if self.debug != True:
                message = "Adlink DLL not found: {}".format(dll_path)
                self.log(message=message)
                raise ValueError(message)
        else:
            self.dll = CDLL(dll_path)
            self.card_id = self.register_card()
            self.configure_card()

        self.ui = None

    def __del__(self):
        """Deregister the card on object deletion."""
        self.release_card()

    def get_qt_ui(self):
        """Return the card's Qt UI widget, creating it on first call.

        Returns:
            Adlink9812UI: The control widget bound to this card.
        """
        if self.ui is None:
            self.ui = Adlink9812UI(card=self)
        return self.ui

    def register_card(self, channel=0):
        """Register the PCI-9812 card with the PCIS-DASK driver.

        Args:
            channel: The card channel to register.

        Returns:
            int: The card id assigned by the driver; negative values indicate an error.
        """
        outp = ctypes.c_int16(
            self.dll.Register_Card(adlink9812_constants.PCI_9812, c_ushort(channel)))
        if outp.value < 0:
            self.log("Register_Card: nonpositive value -> error code:" + str(outp))
        return outp.value

    def release_card(self):
        """Release the card from the driver, logging a non-zero status code."""
        releaseErr = ctypes.c_int16(self.dll.Release_Card(self.card_id))
        if releaseErr.value != 0:
            self.log(message="Release_Card: Non-zero status code:" + str(releaseErr.value))
        return

    def get_card_sample_rate(self, sampling_freq):
        """Query the actual sample rate the card will use for a requested frequency.

        Args:
            sampling_freq: The requested sampling frequency in Hz.

        Returns:
            float: The actual sample rate reported by the driver.

        Raises:
            NameError: ``DLL`` is undefined (it should be ``self.dll``), so this method
                always fails before returning.
        """
        actual = c_double()
        statusCode = ctypes.c_int16(
            DLL.GetActualRate(self.card_id, c_double(sampling_freq), byref(actual)))

        if statusCode.value != 0:
            self.log(message="GetActualRate: Non-zero status code:" + str(statusCode.value))
        return actual.value

    def configure_card(self):
        """Configure the card for recording (software trigger, internal clock)."""
        #Configure card for recording
        configErr = ctypes.c_int16(
            self.dll.AI_9812_Config(
                c_ushort(self.card_id),
                c_ushort(adlink9812_constants.P9812_TRGMOD_SOFT),  #Software trigger mode
                c_ushort(adlink9812_constants.P9812_TRGSRC_CH0),  #Channel 0 
                c_ushort(adlink9812_constants.P9812_TRGSLP_POS),  #Positive edge trigger
                c_ushort(adlink9812_constants.P9812_CLKSRC_INT),  #Internal clock
                c_ushort(0x80),  #Trigger threshold = 0.00V
                c_ushort(0),  #Postcount - setting for Middle/Delay Trigger
            ))

        if configErr.value != 0:
            self.log(message="AI_9812_Config: Non-zero status code:" + str(configErr.value))
        return

    def convert_to_volts(self, inputBuffer, outputBuffer, buffer_size):
        """Convert raw 16-bit A/D samples to voltages using the driver's scaling.

        Args:
            inputBuffer: ctypes array of raw 16-bit A/D values.
            outputBuffer: ctypes array that receives the converted voltages.
            buffer_size: Number of samples to convert.
        """
        convertErr = ctypes.c_int16(
            self.dll.AI_ContVScale(
                c_ushort(self.card_id),  #CardNumber
                c_ushort(adlink9812_constants.AD_B_1_V),  #AdRange
                inputBuffer,  #DataBuffer   - array storing raw 16bit A/D values
                outputBuffer,  #VoltageArray - reference to array storing voltages
                c_uint32(buffer_size)  #Sample count - number of samples to be converted
            ))

        if convertErr.value != 0:
            self.log(message="AI_ContVScale: Non-zero status code:" + str(convertErr.value))
        return

    def synchronous_analog_input_read(self, sample_freq, sample_count, verbose=False, channel=0):
        """Perform a single synchronous (blocking) continuous read from one channel.

        Args:
            sample_freq: Sampling frequency in Hz.
            sample_count: Number of samples to acquire.
            verbose: Unused; retained for call compatibility.
            channel: Input channel to read from.

        Returns:
            np.ndarray: The acquired samples converted to volts.
        """
        #Initialize Buffers
        #databuffer for holding A/D samples + metadata bits
        dataBuff = (c_ushort * sample_count)()
        #voltageArray for holding converted voltage values
        voltageOut = (c_double * sample_count)()

        #Sample data, Mode: Synchronous
        readErr = ctypes.c_int16(
            self.dll.AI_ContReadChannel(
                c_ushort(self.card_id),  #CardNumber
                c_ushort(channel),  #Channel
                c_ushort(adlink9812_constants.AD_B_1_V),  #AdRange
                dataBuff,  #Buffer
                c_uint32(sample_count),  #ReadCount
                c_double(sample_freq),  #SampleRate (Hz)
                c_ushort(adlink9812_constants.SYNCH_OP)  #SyncMode
            ))

        if readErr.value != 0:
            self.log(message="AI_ContReadChannel: Non-zero status code:" + str(readErr.value))

        #Convert to volts
        self.convert_to_volts(dataBuff, voltageOut, sample_count)
        return np.asarray(voltageOut)

    def asynchronous_double_buffered_analog_input_read(self,
                                                       sample_freq,
                                                       sample_count,
                                                       card_buffer_size=500000,
                                                       verbose=False,
                                                       channel=0):
        '''Perform a non-triggered double-buffered asynchronous continuous read.

		Reads into the card's internal double buffer, transferring half-buffers into
		user buffers as they become ready, then converts the accumulated raw samples
		to volts.

		Args:
			sample_freq: Sampling frequency in Hz.
			sample_count: Number of samples to acquire.
			card_buffer_size: Size of the card's internal buffer, in samples.
			verbose: If True, log additional driver status information.
			channel: Input channel to read from.

		Returns:
			np.ndarray: The acquired samples converted to volts.

		Steps: [Adlink PCIS-DASK manual,page 47]

		1. AI_XXXX_Config
			Configure the card for the asynchronous mode

		2. AI_AsyncDblBufferMode 
			Enable double buffered mode

		3. AI_ContReadChannel
			Read from a single channel (=0)

		4. while not stop:

			4.1 if (AI_AsyncDblBufferHaldReady):   #Check if buffer is half full]
				
				4.1.1 AI_AsyncDblBufferTransfer	   #Transfer data from card buffer into user buffer
			
		5. AI_AsyncClear
		6. Convert all data to volts and return

		'''

        #AI_AsyncDblBufferMode - initialize Double Buffer Mode
        buffModeErr = ctypes.c_int16(
            self.dll.AI_AsyncDblBufferMode(c_ushort(self.card_id), ctypes.c_bool(1)))
        if verbose or buffModeErr.value != 0:
            self.log(message="AI_AsyncDblBufferMode: Non-zero status code" + str(buffModeErr.value))

        #card buffer
        cardBuffer = (c_ushort * card_buffer_size)()

        #user buffers
        user_buffer_size = card_buffer_size // 2  #half due to being full when buffer is read
        nbuff = int(math.ceil(sample_count / float(user_buffer_size)))

        # uBs = [(c_double*user_buffer_size)()]*nbuff
        uBs = []
        print(uBs)
        # oBs = [(c_double*user_buffer_size)()]*nbuff
        oBs = []
        if verbose:
            self.log(message="Number of user buffers:" + str(nbuff))

        #AI_ContReadChanne

        readErr = ctypes.c_int16(
            self.dll.AI_ContReadChannel(
                c_ushort(self.card_id),  #CardNumber
                c_ushort(channel),  #Channel
                c_ushort(adlink9812_constants.AD_B_1_V),  #AdRange
                cardBuffer,  #Buffer
                c_uint32(card_buffer_size),  #ReadCount
                c_double(sample_freq),  #SampleRate (Hz)
                c_ushort(adlink9812_constants.ASYNCH_OP)  #SyncMode - Asynchronous
            ))

        if verbose or readErr.value != 0:
            self.log(message="AI_ContReadChannel: Non-zero status code" + str(readErr.value))

        #AI_AsyncDblBufferHalfReader
        #I16 AI_AsyncDblBufferHalfReady (U16 CardNumber, BOOLEAN *HalfReady,BOOLEAN *StopFlag)

        for i in range(nbuff):
            currentBuffer = (c_double * user_buffer_size)()
            halfReady = c_bool(0)
            stopFlag = c_bool(0)
            while halfReady.value != True:
                buffReadyErr = ctypes.c_int16(
                    self.dll.AI_AsyncDblBufferHalfReady(c_ushort(self.card_id),
                                                        ctypes.byref(halfReady),
                                                        ctypes.byref(stopFlag)))
                if buffReadyErr.value != 0:
                    self.log(message="buffReadErr:" + str(buffReadyErr.value))
                    self.log(message="HalfReady:" + str(halfReady.value))

            #AI_AsyncDblBufferTransfer
            #I16 AI_AsyncDblBufferTransfer (U16 CardNumber, U16 *Buffer)
            buffTransferErr = ctypes.c_int16(
                self.dll.AI_AsyncDblBufferTransfer(c_ushort(self.card_id),
                                                   ctypes.byref(currentBuffer)))
            uBs.append(currentBuffer)
            if buffTransferErr.value != 0:
                self.log(message="buffTransferErr:" + str(buffTransferErr.value))

        accessCnt = ctypes.c_int32(0)
        clearErr = ctypes.c_int16(self.dll.AI_AsyncClear(self.card_id, ctypes.byref(accessCnt)))
        if verbose:
            self.log(message="AI_AsyncClear,AccessCnt:" + str(accessCnt.value))

        #concatenate user buffer onto existing numpy array
        #reinitialize user buffer

        for i in range(nbuff):
            oB = (c_double * user_buffer_size)()
            convertErr = ctypes.c_int16(
                self.dll.AI_ContVScale(
                    c_ushort(self.card_id),  #CardNumber
                    c_ushort(adlink9812_constants.AD_B_1_V),  #AdRange
                    uBs[i],  #DataBuffer   - array storing raw 16bit A/D values
                    oB,  #VoltageArray - reference to array storing voltages
                    c_uint32(user_buffer_size)  #Sample count - number of samples to be converted
                ))
            oBs.append(oB)
            if convertErr.value != 0:
                self.log(message="AI_ContVScale: Non-zero status code:" + str(convertErr.value))
        return np.concatenate(oBs)

    @staticmethod
    def get_times(dt, nsamples):
        """Return a list of sample timestamps.

        Args:
            dt: Time between samples, in seconds.
            nsamples: Number of samples.

        Returns:
            list: Timestamps ``[0, dt, 2*dt, ...]`` of length ``nsamples``.
        """
        return [i * dt for i in range(nsamples)]

    def capture(self, sample_freq, sample_count, verbose=False):
        """Capture a voltage trace, choosing the read mode by sample count.

        In debug mode returns synthetic random data. Otherwise uses an asynchronous
        double-buffered read for large captures (> 100000 samples) and a synchronous
        read for smaller ones.

        Args:
            sample_freq: Sampling frequency in Hz; must satisfy ``1 < f <= 2e7``.
            sample_count: Number of samples to acquire.
            verbose: If True, log additional driver status information.

        Returns:
            tuple: A ``(voltages, dt)`` pair, where ``voltages`` is an ``np.ndarray``
            and ``dt`` is the sample interval in seconds.

        Raises:
            AssertionError: ``sample_freq`` is outside the range ``(1, 2e7]``.
        """
        assert (sample_freq <= int(2e7) and sample_freq > 1)
        dt = 1.0 / sample_freq
        if self.debug:

            debug_out = (2.0 * np.random.rand(sample_count)) - 1.0
            return debug_out, dt

        elif sample_count > 100000:
            return self.asynchronous_double_buffered_analog_input_read(sample_freq=sample_freq,
                                                                       sample_count=sample_count,
                                                                       verbose=verbose), dt
        else:
            return self.synchronous_analog_input_read(sample_freq=sample_freq,
                                                      sample_count=sample_count,
                                                      verbose=verbose), dt


class Adlink9812UI(QtWidgets.QWidget, UiTools):
    """Qt control widget for an :class:`Adlink9812` card.

    Exposes capture settings and DLS post-processing stages (raw voltage, voltage
    difference, photon counts, autocorrelation) and runs captures on a worker thread.
    """

    def __init__(self, card, parent=None, debug=False, verbose=False):
        """Build the widget and wire up the capture/settings controls.

        Args:
            card: The :class:`Adlink9812` instance to control.
            parent: Optional parent widget.
            debug: Enable debug behaviour in the UI.
            verbose: Enable verbose logging in the UI.

        Raises:
            ValueError: ``card`` is not an :class:`Adlink9812` instance.
        """
        if not isinstance(card, Adlink9812):
            raise ValueError("Object is not an instance of the Adlink9812 Daq")
        super(Adlink9812UI, self).__init__()
        self.card = card
        self.parent = parent
        self.debug = debug
        self.verbose = verbose
        self.log = self.card.log

        #Initialize the capture thread handle
        self.capture_thread = None

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'adlink9812.ui'), self)

        #daq_settings_layout
        self.sample_freq_textbox.textChanged.connect(self.set_sample_freq)
        self.sample_count_textbox.textChanged.connect(self.set_sample_count)
        self.series_name_textbox.textChanged.connect(self.set_series_name)

        #processing_stages_layout
        # self.threshold_textbox.textChanged.connect(self.set_threshold)
        self.binning_textbox.textChanged.connect(self.set_bin_width)
        self.average_textbox.textChanged.connect(self.set_averaging)

        #actions_layout
        self.capture_button.clicked.connect(self.threaded_capture)
        self.count_rate_button.clicked.connect(self.current_count_rate)

        self.set_sample_freq()
        self.set_sample_count()
        self.set_series_name()
        self.set_bin_width()
        self.set_averaging()
        # self.set_threshold()

    def set_averaging(self):
        """Parse the number of averaging runs from the averaging text box."""
        try:
            self.averaging_runs = int(self.average_textbox.text())
        except:
            self.log(message="Failed parsing average_textbox value: {0}".format(
                self.average_textbox.text()))
        return

    # def set_threshold(self):
    # 	try:
    # 		self.difference_threshold = float(self.threshold_textbox.text())
    # 	except Exception, e:
    # 		print "Failed parsing threshold_textbox value: {0}".format(self.threshold_textbox.text())
    # 	return

    def set_bin_width(self):
        """Parse the time bin width (seconds) from the binning text box."""
        try:
            self.bin_width = float(self.binning_textbox.text())
        except Exception as e:
            self.log(
                message="Failed parsing binning_threshold: {0}".format(self.binning_textbox.text()))
        return

    def set_sample_freq(self):
        """Parse the sampling frequency (entered in MHz) from its text box, in Hz."""
        MHz = 1e6
        try:
            self.sample_freq = int(float(self.sample_freq_textbox.text()) * MHz)
        except Exception as e:
            self.log(message="Failed parsing sample_freq_textbox value to float:" +
                     str(self.sample_freq_textbox.text()))
            return
        return

    def set_sample_count(self):
        """Parse the number of samples to acquire from the sample-count text box."""
        try:

            self.sample_count = int(float(self.sample_count_textbox.text()))
            if self.verbose > 0:
                print("Sample Count: {0} [Counts]".format(self.sample_count))

            self.sample_count = int(float(self.sample_count_textbox.text()))

        except Exception as e:
            self.log(message="Failed parsing sample count to int:" +
                     self.sample_freq_textbox.text())
        return

    def set_series_name(self):
        """Set the HDF5 series/group name from the series-name text box."""
        self.series_group = self.series_name_textbox.text()
        return

    def save_data(self, data, datatype, group, metadata=None):
        """Save a dataset into an HDF5 group with units and axis-label metadata.

        Args:
            data: The array to store.
            datatype: One of the valid datatypes (e.g. ``"raw_voltage"``,
                ``"photon_counts"``, ``"autocorrelation"``); selects the attached
                units and axis labels.
            group: The HDF5 group to create the dataset in.
            metadata: Optional dict of extra attributes to attach.

        Raises:
            AssertionError: ``datatype`` is not in the valid datatype list.
            ValueError: ``datatype`` is unrecognised by the attribute switch.
        """
        VALID_DATATYPES = [
            "raw_voltage", "voltage_difference", "photon_counts", "autocorrelation",
            "autocorrelation_stdev", "autocorrelation_skew"]

        attrs = {"device": "adlink9812", "datatype": datatype}
        #push additional metadata
        if metadata != None:
            attrs.update(metadata)
        assert (datatype in VALID_DATATYPES)
        if datatype == "raw_voltage":
            attrs.update({"_units": "volts", "X label": "Sample Index", "Y label": "Voltage [V]"})
        elif datatype == "voltage_difference":
            attrs.update({
                "_units": "none",
                "X label": "Sample Index",
                "Y label": "Normalized Voltage Difference [V]"})
        elif datatype == "photon_counts":
            attrs.update({"_units": "count", "X label": "Time [s]", "Y label": "Photon Count"})
        elif datatype == "autocorrelation":
            attrs.update({
                "_units": "none",
                "X label": "Time [s]",
                "Y label": "Intensity Autocorrelation g2 [no units]"})
        elif datatype == "autocorrelation_stdev":
            attrs.update({
                "_units": "none",
                "X label": "Time [s]",
                "Y label": "Autocorrelation Stdev [no units]"})
        elif datatype == "autocorrelation_skew":
            attrs.update({
                "_units": "none",
                "X label": "Time [s]",
                "Y label": "Autocorrelation skew [no units]"})

        else:
            raise ValueError("adlink9812.save_data - Invalid datatype")
        group.create_dataset(datatype + "_%d", data=data, attrs=attrs)
        group.file.flush()
        return

    def postprocess(self, voltages, dt, save, group, metadata):
        """Run the DLS post-processing chain on a voltage trace.

        Computes the voltage difference, thresholds it to photon counts, bins the
        counts, and computes the intensity autocorrelation, optionally saving each
        enabled stage.

        Args:
            voltages: The raw voltage trace.
            dt: Sample interval in seconds.
            save: If True, save the stages whose checkboxes are enabled.
            group: HDF5 group to save into.
            metadata: Base metadata dict attached to saved datasets.

        Returns:
            tuple: A ``(times, autocorrelation)`` pair (delay axis and g2 values, with
            the zero-delay point dropped).
        """
        attributes = dict(metadata)

        #initial system parameters
        sample_count = len(voltages)
        sample_time = dt * sample_count

        #take difference of voltages
        rounded_diff = dls_signal_postprocessing.signal_diff(voltages)

        #thresholding
        thresholded = np.absolute(rounded_diff).astype(int)

        #binning
        time_bin_width = self.bin_width
        index_bin_width = dls_signal_postprocessing.binwidth_time_to_index(time_bin_width, dt)
        binned_counts = dls_signal_postprocessing.binning(thresholded=thresholded,
                                                          index_bin_width=index_bin_width)
        time_bins = time_bin_width * np.arange(0, len(binned_counts))

        total_counts = np.sum(binned_counts)
        count_rate = float(total_counts) / float(sample_time)
        self.log("\tCounts: {0:.3g}, Rate:{1:.3g}".format(total_counts, count_rate))
        #correlation
        #note - truncating delay t=0, this is the zero frequency - not interesting
        times = time_bins[1:]
        autocorrelation = dls_signal_postprocessing.autocorrelation(binned_counts)[1:]

        #save data
        attributes.update({"averaged_data": "False"})
        stages = [
            ("raw_voltage", self.raw_checkbox.isChecked(), voltages, attributes),
            ("voltage_difference", self.difference_checkbox.isChecked(), rounded_diff, attributes),
            ("photon_counts", self.binning_checkbox.isChecked(),
             np.vstack((time_bins, binned_counts)), attributes),
            ("autocorrelation", self.correlate_checkbox.isChecked(),
             np.vstack((times, autocorrelation)), attributes)]
        for (datatype, checked, data, mdata) in stages:
            if save == True and checked == True:
                self.save_data(datatype=datatype, data=data, group=group, metadata=mdata)
        return times, autocorrelation

    def current_count_rate(self):
        """Capture a short fixed trace and compute the current photon count rate.

        Returns:
            tuple: A ``(total_counts, count_rate)`` pair, where ``count_rate`` is in
            counts per second.
        """
        #measure for 0.05s for sampling photon count

        #fixed values of sampling - we want to keep things easy
        frequency = 2e7  #20MHz
        sample_count = int(1e6)  #0.05s
        voltages, dt = self.card.capture(sample_freq=frequency, sample_count=sample_count)
        sample_time = dt * sample_count
        #convert rounded difference to integers
        thresholded = np.absolute(dls_signal_postprocessing.signal_diff(voltages)).astype(int)
        total_counts = np.sum(thresholded)
        count_rate = total_counts / sample_time
        self.log("Total Counts: {0} [counts], Rate: {1} [counts/s]".format(
            int(total_counts), count_rate))
        return total_counts, count_rate

    def capture(self, metadata=None):
        """Run a capture from the UI, post-process it, and optionally save/average.

        Reads the sampling settings and stage checkboxes from the widget. If averaging
        is enabled it captures ``averaging_runs`` traces and saves the mean, standard
        deviation and skew of the autocorrelation.

        Args:
            metadata: Optional base metadata dict merged with the description text.
        """
        save = self.save_checkbox.isChecked()
        plot = self.plot_checkbox.isChecked()
        average = self.average_checkbox.isChecked()

        message = '''
 Capture started
 SamplingFreq (Hz):{0}
 SampleCount (counts):{1}
 SeriesName:{2}
 Plot trace:{3}
 Save trace:{4}
 Averaging:{5}'''.format(self.sample_freq, self.sample_count, self.series_group, plot, save,
                         average)
        self.log(message=message, level="info")

        if save:
            try:
                self.datafile
            except AttributeError:
                self.datafile = pyopenlab.datafile.current()
            dg = self.datafile.require_group(self.series_group)
        else:
            dg = None

        self.description = self.comment_textbox.document().toPlainText()
        self.log(message="Description:{}".format(self.description))

        if metadata is not None and type(metadata) == dict:
            self.base_metadata = metadata
        else:
            self.base_metadata = dict()
        self.base_metadata.update({"description": self.description})

        #Averaging run:
        if average == False:
            voltages, dt = self.card.capture(sample_freq=self.sample_freq,
                                             sample_count=self.sample_count)
            times, autocorrelation = self.postprocess(voltages=voltages,
                                                      dt=dt,
                                                      save=save,
                                                      group=dg,
                                                      metadata=self.base_metadata)
            acs_array = None
        elif average == True:
            self.log(
                message=
                '''Averaging enabled - checkbox options reset:\n\traw_checkbox:{0} -> False\n\tdifference_checkbox {1} -> False\n\tbinning_checkbox {2} -> False'''
                .format(self.raw_checkbox.isChecked(), self.difference_checkbox.isChecked(),
                        self.binning_checkbox.isChecked()),
                level="warn")
            self.raw_checkbox.setChecked(False)
            self.difference_checkbox.setChecked(False)
            self.binning_checkbox.setChecked(False)

            acs_array = None
            for i in range(self.averaging_runs):
                start_time = timeit.default_timer()

                self.card.log(message="---Iteration:{0}".format(i))

                voltages, dt = self.card.capture(sample_freq=self.sample_freq,
                                                 sample_count=self.sample_count)
                times, autocorrelation = self.postprocess(voltages=voltages,
                                                          dt=dt,
                                                          save=save,
                                                          group=dg,
                                                          metadata=self.base_metadata)

                if acs_array is None:
                    acs_array = np.zeros(shape=(self.averaging_runs, len(autocorrelation)),
                                         dtype=np.float32)

                acs_array[i, :] = autocorrelation

                exec_time = timeit.default_timer() - start_time
                self.log(message="/--Iteration:{0} [T_exec:{1:.3g}]".format(i, exec_time))
            #compute mean, stdev and skew for all data
            mean_acs = np.mean(acs_array, axis=0)
            assert (len(mean_acs) == len(times))
            stdev_acs = np.std(acs_array, axis=0)
            skew_acs = scipy.stats.skew(acs_array, axis=0)

            averaged_metadata = dict(self.base_metadata)
            averaged_metadata.update({"averaged_data": "True"})
            self.save_data(data=np.vstack((times, mean_acs)),
                           datatype="autocorrelation",
                           group=dg,
                           metadata=averaged_metadata)
            self.save_data(data=np.vstack((times, stdev_acs)),
                           datatype="autocorrelation_stdev",
                           group=dg,
                           metadata=averaged_metadata)
            self.save_data(data=np.vstack((times, skew_acs)),
                           datatype="autocorrelation_skew",
                           group=dg,
                           metadata=averaged_metadata)

        return

    def threaded_capture(self, settings=None):
        """Start :meth:`capture` on a background thread unless one is already running.

        Args:
            settings: Optional metadata passed through to :meth:`capture`.
        """
        if isinstance(self.capture_thread, threading.Thread) and self.capture_thread.is_alive():
            self.card.log(message="Capture already running!", level="info")
            return
        self.capture_thread = threading.Thread(target=self.capture, args=(settings,))
        self.capture_thread.start()


if __name__ == "__main__":

    #debug mode enabled - won't try to picj up card - will generate data
    card = Adlink9812("C:\ADLINK\PCIS-DASK\Lib\PCI-Dask64.dll", debug=True)
    app = get_qt_app()
    ui = Adlink9812UI(card=card, debug=False)
    ui.show()
    sys.exit(app.exec_())
