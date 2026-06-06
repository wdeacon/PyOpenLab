"""Interface for National Instruments DAQ devices via the PyDAQmx wrapper.

Note:
    ``setup_multi_ai_cont`` and ``read_multi_ai_cont`` reference ``self.device``,
    which is never assigned (only ``self.device_id`` exists). Calling either method
    therefore raises ``AttributeError``; the continuous-acquisition path is broken.
"""

__author__ = 'alansanders'

import numpy as np
from pydaqmx import *
import pydaqmx as pdmx  # pointess line of code ?

from pyopenlab.instrument import Instrument


class NIDAQ(Instrument):
    """An interface for NIDAQ devices."""

    def __init__(self, device_id):
        """Initialize the DAQ interface.

        Args:
            device_id: A string identifier for the device, e.g. ``'Dev1'``.
        """
        super(NIDAQ, self).__init__()
        self.device_id = device_id
        self.current_task = None
        self.channels = None
        self.sample_rate = None
        self.time_interval = None
        self.num_points = None

    def setup_multi_ai(self, channels, sample_rate, time_interval):
        """Set up the DAQ device for multiple-channel analog input.

        In this implementation the task is not started, only set up with the task
        committed to improve start speed.

        Args:
            channels: An iterable of channel identifiers, e.g. ``0, 1, 2, ...``.
            sample_rate: The sampling frequency in Hz.
            time_interval: The time interval over which data is sampled, in seconds.
        """
        num_samples = int(sample_rate *
                          time_interval)  # this is the number of points expected per channel
        while num_samples % len(
                channels
        ) != 0:  # the number of samples must be evenly divisable between all channels
            num_samples += 1  # the number of samples is increased until all channels are equal
        self.num_samples = num_samples
        self.time_interval = time_interval
        analog_input = Task()
        s = ''
        for ch in channels:
            s += '{0}/ai{1},'.format(self.device_id, str(ch))
        analog_input.CreateAIVoltageChan(s, "", DAQmx_Val_Cfg_Default, -10.0, 10.0, DAQmx_Val_Volts,
                                         None)
        analog_input.CfgSampClkTiming("", sample_rate, DAQmx_Val_Rising, DAQmx_Val_FiniteSamps,
                                      num_samples)
        analog_input.TaskControl(DAQmx_Val_Task_Commit)
        self.current_task = analog_input
        self.channels = channels

    def read_multi_ai(self):
        """Read from a DAQ device previously set up using ``setup_multi_ai``.

        The task is started and then stopped once complete. The data is then parsed
        and returned.

        Returns:
            tuple: A ``(time, data)`` pair, where ``time`` is the sample-time axis
            (``np.ndarray``) and ``data`` is a list of per-channel arrays.
        """
        analog_input = self.current_task
        read = int32()
        total_samples = self.num_samples * len(self.channels)
        data = np.zeros((total_samples,), dtype=np.float64)
        time = np.linspace(0, self.time_interval, self.num_samples)
        analog_input.StartTask()
        analog_input.ReadAnalogF64(
            self.num_samples,  #DAQmx_Val_Auto,
            -1,  #DAQmx_Val_WaitInfinitely,
            DAQmx_Val_GroupByChannel,
            data,
            total_samples,
            byref(read),
            None)
        analog_input.StopTask()
        data = self._parse_data(self.channels, data)
        return time, data

    def setup_multi_ai_cont(self, channels, sample_rate, time_interval):
        """Set up continuous multiple-channel analog input clocked by a counter output.

        Configures an analog-input task together with a retriggerable counter-output
        task that drives the input sample clock, then starts both for continuous
        sampling.

        Args:
            channels: An iterable of channel identifiers, e.g. ``0, 1, 2, ...``.
            sample_rate: The sampling frequency in Hz.
            time_interval: The time interval over which data is sampled, in seconds.

        Raises:
            AttributeError: ``self.device`` is referenced but never assigned (only
                ``self.device_id`` exists), so this method fails before configuring
                the task.
        """
        analog_input = Task()
        analog_counter = Task()
        num_samples = int(sample_rate *
                          time_interval)  # this is the number of points expected per channel
        while num_samples % len(channels) != 0:
            num_samples += 1
        self.num_samples = num_samples
        self.time_interval = time_interval
        # DAQmx Configure Code
        s = ''
        for ch in channels:
            s += self.device + '/ai' + str(ch) + ','
        # create an analog input channel named aiChannel
        analog_input.CreateAIVoltageChan(s, "aiChannel", DAQmx_Val_Cfg_Default, -10.0, 10.0,
                                         DAQmx_Val_Volts, None)
        # create the clock for my analog input task
        analog_input.CfgSampClkTiming("/%s/Ctr0InternalOutput" % self.device, sample_rate,
                                      DAQmx_Val_Rising, DAQmx_Val_ContSamps, num_samples)
        # configure analog input buffer
        #analog_input.SetBufferAttribute(DAQmx_Buf_Input_BufSize, num_samples+1000)
        # create a counter output channel named coChannel */
        analog_counter.CreateCOPulseChanFreq('/%s/ctr0' % self.device, "coChannel", DAQmx_Val_Hz,
                                             DAQmx_Val_Low, 0, sample_rate, 0.5)

        # create the clock for my counter output task*/
        analog_counter.CfgImplicitTiming(DAQmx_Val_FiniteSamps, num_samples)
        analog_counter.CfgDigEdgeStartTrig('/%s/PFI0' % self.device, DAQmx_Val_Rising)
        analog_counter.SetTrigAttribute(DAQmx_StartTrig_Retriggerable, True)
        # DAQmx Start Code
        analog_input.StartTask()
        analog_counter.StartTask()
        #analog_input.TaskControl(DAQmx_Val_Task_Commit)
        self.current_task = analog_input
        self.current_counter = analog_counter
        self.channels = channels

    def read_multi_ai_cont(self):
        """Read from a continuous task previously set up using ``setup_multi_ai_cont``.

        Reads the next block of samples without starting or stopping the task, then
        parses and returns it.

        Returns:
            tuple: A ``(time, data)`` pair, where ``time`` is the sample-time axis
            (``np.ndarray``) and ``data`` is a list of per-channel arrays.

        Raises:
            AttributeError: ``setup_multi_ai_cont`` cannot complete (it references the
                unassigned ``self.device``), so a continuous task is never available.
        """
        analog_input = self.current_task
        read = int32()
        total_samples = self.num_samples * len(self.channels)
        data = np.zeros((total_samples,), dtype=np.float64)
        time = np.linspace(0, self.time_interval, self.num_samples)
        analog_input.ReadAnalogF64(
            self.num_samples,  #DAQmx_Val_Auto,
            -1,  #DAQmx_Val_WaitInfinitely,
            DAQmx_Val_GroupByChannel,
            data,
            total_samples,
            byref(read),
            None)
        #print "Acquired %d points"%read.value
        data = self._parse_data(self.channels, data)
        return time, data

    def _parse_data(self, channels, data):
        """Split interleaved readout data into per-channel arrays.

        The readout data is organised into an array ``n * m`` long, where ``n`` is the
        number of channels and ``m`` is the number of samples per channel. This method
        splits the readout data into ``n`` segments, one per channel.

        Args:
            channels: The iterable of channel identifiers used for the acquisition.
            data: The flat readout array to split.

        Returns:
            list: A list of ``n`` arrays, one per channel.
        """
        data = np.split(data, len(channels))
        return data

    def clear_multi_ai(self):
        """Clear the previously committed task as set up in ``setup_multi_ai``."""
        self.current_task.TaskControl(DAQmx_Val_Task_Unreserve)

    def stop_current_task(self):
        """Force the current task to stop."""
        self.current_task.StopTask()


class Itask(Task):
    """Wrap a NIDAQ Task object so multiple tasks can run without re-initialising.

    Allows a task to be configured once and re-run without re-initialising each time
    the task needs to be run.
    """

    def __init__(self):
        """Initialize the task wrapper with no configured mode."""
        Task.__init__(self)
        self.mode = None

    def setupmulti_ao(self, device_id, channels, minoutput, maxoutput):
        """Set up a task/channel in the analog output configuration.

        Args:
            device_id (string): the name of the device setup in NI Max
                                This should alawys be pulled straight from the 
                                NIDAQ object via self.device_id
            channels(list): The channel number you wish to control in list format
            minoutput (float): The minimum voltage the device will apply
            maxoutput(float): the maximum voltage a device can apply"""
        self.device_id = device_id
        self.minoutput = minoutput
        self.maxoutput = maxoutput
        self.channels = channels
        s = ''
        for ch in channels:
            s += '{0}/ao{1},'.format(self.device_id, str(ch))

        self.CreateAOVoltageChan(s, '', self.minoutput, self.maxoutput, DAQmx_Val_Volts, None)
        self.mode = "AO"

    def set_ao(self, value):
        """Set the analog output voltage, in Volts.

        ``setupmulti_ao`` must be called before this method can be used.

        Args:
            value (float): The new output voltage in Volts.

        Raises:
            BaseException: The task is not currently in analog output mode (i.e.
                ``setupmulti_ao`` has not been run)."""

        if self.mode != "AO":
            raise BaseException(
                'This Task is not setup for analog output, the current Task is setup for',
                self.mode)
        value = np.array(float(value))
        self.WriteAnalogF64(len(self.channels), True, 10.0, DAQmx_Val_GroupByChannel, value,
                            byref(int32()), None)


if __name__ == '__main__':
    from time import sleep
    import timeit

    from pylab import plot
    from pylab import show

    def multi_read(d):
        print(5. / 6000)
        d.setup_multi_ai([0, 1, 2, 3, 4], 1e6, 0.001)
        j = 0
        while j < 2:
            time, data = d.read_multi_ai()
            ref = data[0]
            x = data[1] / data[2]
            y = data[3] / data[4]
            new_data = [ref, x, y]
            for i in range(len(new_data)):
                plot(time, new_data[i])
            j += 1
        d.clear_multi_ai()

    def cont_multi_read(d):
        print('should take %s ms' % (1000 * 5. / 6000.))
        d.setup_multi_ai_cont([0, 1, 2, 3, 4], 1e6, 5. / 6000.)
        i = 0
        while i < 10:
            sleep(1)
            time, data = d.read_multi_ai_cont()
            i += 1
        #print timeit.timeit(d.read_multi_ai_cont, number=1000)
        d.clear_multi_ai()
        #d.stop_current_task()

    daq = NIDAQ('Dev2')
    multi_read(daq)
    show()
