"""Instrument wrapper for the Gamari FPGA timetag capture board.

Wraps the ``timetag`` library's :class:`CapturePipeline` to capture photon timetags
and stream them to a file via an external ``timetag-cat`` subprocess.
"""

import os
import subprocess
import time

from timetag.capture_pipeline import CapturePipeline

from pyopenlab.instrument import Instrument


class Timetagger(Instrument):
    """Capture wrapper around the Gamari FPGA timetag :class:`CapturePipeline`.

    Note:
        :meth:`get_qt_ui` is not implemented and raises ``ValueError``.
    """

    def __init__(self, verbose=0):
        """Create the capture pipeline and set the default send-window latency.

        Args:
            verbose: Verbosity level (currently unused).
        """
        self.pipeline = CapturePipeline()
        self._out_file_cat = None
        self._out_file = None
        self.readout_running = False

        #default pipeline latency
        self.pipeline.set_send_window(84)

    def get_qt_ui(self):
        """Return the Qt UI for this instrument.

        Raises:
            ValueError: Always; the Timetagger UI is not implemented.
        """
        raise ValueError("Timetagger UI - Not implemented!")

    def capture(self, integration_time, output_file):
        """Capture timetags for a fixed duration, streaming them to a file.

        Starts the pipeline and the file writeout, blocks for ``integration_time``
        seconds, then stops capture and tears down the writeout subprocess.

        Args:
            integration_time: Capture duration in seconds.
            output_file: Path to write the captured timetag data to.
        """
        self.pipeline.start_capture()
        self.start_writeout(filename=output_file)
        time.sleep(integration_time)
        self.pipeline.stop_capture()
        self._out_file_cat.terminate()
        self._out_file.close()
        self._out_file_cat = None
        self._out_file = None
        self.readout_running = False
        return

    def start_writeout(self, filename):
        """Open the output file and start a ``timetag-cat`` subprocess writing to it.

        Terminates any existing writeout subprocess first and creates the output
        directory if needed.

        Args:
            filename: Path to the output file; ``~`` is expanded and the path normalized.
        """
        if self._out_file_cat is not None:
            self._out_file_cat.terminate()
        filename = os.path.normpath(os.path.expanduser(filename))
        print("Writing captured data to:", filename)
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname) and len(dirname) > 0:
            os.makedirs(dirname)
        self._out_file = open(filename, 'w')
        self._out_file_cat = subprocess.Popen(['timetag-cat'], stdout=self._out_file)
        return


if __name__ == "__main__":
    t = Timetagger()
    from datetime import datetime
    print(datetime.now())
    path = "~/Desktop/timetagger-test.timetag"
    # filename = os.path.normpath(os.path.expanduser(path))
    # print filename
    t.capture(integration_time=3, output_file=path)
    print(datetime.now())
