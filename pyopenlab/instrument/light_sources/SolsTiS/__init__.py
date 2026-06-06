"""MSquared SolsTiS laser wrapper over the SolsTiS 3 TCP/IP protocol.

Not implemented:
    - Wavemeter commands.
    - Report replies for commands that take a while to finish: this needs a change to
      ``read_message``, which currently only reads the last full message.

Note:
    This module targets the original Python 2 / bytes-vs-str behaviour. On Python 3
    ``socket.send`` is passed a ``str`` (must be ``bytes``) and ``read_message`` calls
    ``.split('{')`` on the ``bytes`` returned by ``recv``, so the TCP path raises
    ``TypeError``. These are pre-existing defects left unfixed.
"""
from __future__ import print_function

from future import standard_library

standard_library.install_aliases()
from builtins import str
import collections
import json
import os
import socket
import time

from pyopenlab.instrument import Instrument
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtWidgets
from pyopenlab.utils.gui import uic

BUFFER_SIZE = 1000
TIMEOUT = 10.
MAX_MESSAGE_HISTORY = 10


class SolsTiSParseFail(Exception):
    """Raised when the laser returns a ``parse_fail`` reply, decoding its error code."""

    # updateGUI = QtCore.SIGNAL()

    def __init__(self, dicc):
        exceptionstring = ERROR_CODE[dicc['message']['parameters']['protocol_error'][0]] + \
                          '\n at transmission: ' + str(dicc['message']['transmission_id'][0])

        super(SolsTiSParseFail, self).__init__(exceptionstring)


class SolsTiS(Instrument):
    metadata_property_names = ('laser_status',)

    def __init__(self, address, **kwargs):
        """Connect to the laser and read its initial status.

        Args:
            address: ``(TCP_IP, TCP_PORT)`` tuple identifying the SolsTiS.
            **kwargs: Accepted for compatibility; unused.
        """
        Instrument.__init__(self)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(TIMEOUT)
        self.socket.connect(address)

        self.computerIP = socket.gethostbyname(socket.gethostname())

        self.laser_status = {}
        self._transmission_id = 1
        self.message_out_history = collections.deque(maxlen=MAX_MESSAGE_HISTORY)
        self.message_in_history = collections.deque(maxlen=MAX_MESSAGE_HISTORY)

        self.start_link()
        self.system_status()

    def __del__(self):
        self.socket.close()

    def send_command(self, operation, parameters=None):
        """Send a command using the SolsTiS TCP JSON message structure and read the reply.

        Logs the laser status reported in the reply (resolving numeric status codes via
        ``id_dictionary`` when present).

        Args:
            operation: Name of the operation to send.
            parameters: Optional dict of parameters for the operation.
        """
        if parameters is None:
            self.current_message = {
                "message": {
                    "transmission_id": [self._transmission_id],
                    "op": operation}}
        else:
            self.current_message = {
                "message": {
                    "transmission_id": [self._transmission_id],
                    "op": operation,
                    "parameters": parameters}}

        self.socket.send(json.dumps(self.current_message))

        self.message_out_history.append(self.current_message)
        self._transmission_id += 1

        self.read_message()

        if 'status' in list(self.message_in_history[-1]['message']['parameters'].keys()):
            status = self.message_in_history[-1]['message']['parameters']['status']

            if isinstance(status, str):
                self._logger.debug(operation + ': ' + status)
            else:
                self._logger.debug(operation + ': ' +
                                   id_dictionary.get(operation, {})['status'][status[0]])

    def read_message(self):
        """Read ``BUFFER_SIZE`` bytes and append the last full message to ``message_in_history``.

        Raises:
            SolsTiSParseFail: If the laser reports a ``parse_fail`` operation.
        """
        self.current_reply = self.socket.recv(BUFFER_SIZE)
        if len(self.current_reply.split('{')) != len(self.current_reply.split('}')):
            self._logger.warn('You have not read a full number of messages')

        self.message_in_history.append(
            json.loads('{' + self.current_reply.lstrip('{').split('}{')[-1]))

        if self.message_in_history[-1]['message']['op'] == 'parse_fail':
            raise SolsTiSParseFail(self.message_in_history[-1])

    def start_link(self):
        """Establish the control link, sending this computer's IP to the laser."""
        self.send_command("start_link", {"ip_address": self.computerIP})

    def ping(self, text):
        """Ping the laser with ``text``.

        Args:
            text: Arbitrary string to echo.

        Returns:
            The ``text_out`` value echoed back by the laser.
        """
        self.send_command("ping", {"text_in": text})

        return self.message_in_history[-1]['message']['parameters']['text_out']

    def change_wavelength(self, l):
        """Tune to a wavelength via the wavemeter and refresh status on success.

        Args:
            l: Target wavelength in nm.
        """
        self.send_command("set_wave_m", {"wavelength": [l]})

        time.sleep(1)
        if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
            self.system_status()

    def check_wavelength(self):
        """Poll the wavemeter and cache the current wavelength in ``laser_status``."""
        self.send_command("poll_wave_m")

        if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
            self.laser_status['wavelength'] = \
                self.message_in_history[-1]['message']['parameters']['current_wavelength'][0]

    def stop_tuning(self):
        """Abort an in-progress wavelength move."""
        self.send_command("stop_move_wave_t")

    def tune_etalon(self, val):
        """Set the etalon tuning.

        Args:
            val: Etalon setting (percentage of full range).
        """
        self.send_command("tune_etalon", {"setting": [val]})

    def tune_cavity(self, val):
        """Set the reference-cavity tuning.

        Args:
            val: Cavity setting (percentage of full range).
        """
        self.send_command("tune_cavity", {"setting": [val]})

    def fine_tune_cavity(self, val):
        """Set the fine reference-cavity tuning.

        Args:
            val: Fine cavity setting.
        """
        self.send_command("fine_tune_cavity", {"setting": [val]})

    def tune_resonator(self, val):
        """Set the resonator tuning.

        Args:
            val: Resonator setting (percentage of full range).
        """
        self.send_command("tune_resonator", {"setting": [val]})

    def fine_tune_resonator(self, val):
        """Set the fine resonator tuning.

        Args:
            val: Fine resonator setting.
        """
        self.send_command("fine_tune_resonator", {"setting": [val]})

    def etalon_lock(self, val):
        """Turn the etalon lock on or off and cache the state on success.

        Args:
            val: ``'on'`` or ``'off'``.

        Raises:
            ValueError: If ``val`` is not ``'on'`` or ``'off'``.
        """
        if val not in ['off', 'on']:
            raise ValueError('Lock can only be set to "off" or "on"')
        else:
            self.send_command("etalon_lock", {"operation": val})

            if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
                self.laser_status['etalon_lock'] = val

    def etalon_lock_status(self):
        """Query the etalon-lock condition and cache it in ``laser_status``."""
        self.send_command("etalon_lock_status")

        if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
            self.laser_status['etalon_lock'] = self.message_in_history[-1]['message']['parameters'][
                'condition']

    def cavity_lock(self, val):
        """Turn the reference-cavity lock on or off and cache the state on success.

        Args:
            val: ``'on'`` or ``'off'``; any other value is logged as a warning and ignored.
        """
        if val not in ['off', 'on']:
            self._logger.warn('Lock can only be set to "off" or "on"')
        else:
            self.send_command("cavity_lock", {"operation": val})

            if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
                self.laser_status['ref_cavity_lock'] = val

    def cavity_lock_status(self):
        """Query the reference-cavity lock condition and cache it in ``laser_status``."""
        self.send_command("cavity_lock_status")

        if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
            self.laser_status['ref_cavity_lock'] = self.message_in_history[-1]['message'][
                'parameters']['condition']

    def system_status(self):
        """Query the full laser status and store every reported field in ``laser_status``."""
        self.send_command("get_status")

        if self.message_in_history[-1]['message']['parameters']['status'][0] == 0:
            status = self.message_in_history[-1]['message']['parameters']
            for ii in status:
                if type(status[ii]) == list:
                    self.laser_status[ii] = status[ii][0]
                else:
                    self.laser_status[ii] = status[ii]

        # self.updateGUI.emit()

    def get_qt_ui(self):
        """Return a :class:`SolsTiSUI` control widget for this laser."""
        return SolsTiSUI(self)

        # def settings(self, save=False):
        #     path = os.path.dirname(os.path.realpath(__file__))
        #     name = self.id
        #     if save:
        #         dicc = guisettings.guisave2(self, QtCore.QSettings(path + '/instr_settings/%s.ini' %name, QtCore.QSettings.IniFormat))
        #         return dicc
        #     else:
        #         guisettings.guirestore2(self, QtCore.QSettings(path + '/instr_settings/%s.ini' %name, QtCore.QSettings.IniFormat))
        #         self.change_wavelength(self.laser_status['wavelength'])
        #         self.updateGUI.emit()


class SolsTiSUI(QtWidgets.QWidget):
    """Qt control panel for a :class:`SolsTiS`: wavelength entry, locks, and status monitor."""

    def __init__(self, solstis):
        assert isinstance(solstis, SolsTiS), "instrument must be a SolsTiS"
        super(SolsTiSUI, self).__init__()

        self.SolsTiS = solstis
        self.signal = QtCore.SIGNAL('SolsTiSGUIupdate')
        self.SolsTiSMonitorThread = None

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'SolsTiS.ui'), self)

        self.checkBoxSolsTiSLockMonitor.stateChanged.connect(self.SolsTiSLockMonitor)
        self.checkBoxSolsTiSEtalonLock.stateChanged.connect(self.SolsTiSLockEtalon)
        self.checkBoxSolsTiSCavityLock.stateChanged.connect(self.SolsTiSLockCavity)
        self.lineEditSolsTiSWL.returnPressed.connect(self.SolsTiSWL)
        self.pushButtonSolsTiSstatusMonitor.clicked.connect(self.SolsTiSMonitor)
        self.pushButtonSolsTiSstopMonitor.clicked.connect(self.SolsTiSMonitorStop)

        # self.SolsTiS.updateGUI.connect(self.updateGUI)

    def SolsTiSLockMonitor(self):
        # ADD A SEcTION THAT CHECKS THAT THE ETALON VOLTAGE DOESN'T GO TOO FAR AWAY
        if self.checkBoxSolsTiSEtalonLock.isChecked():
            self.SolsTisLockThread = SolsTiSLockThread(self.SolsTiS)
            self.SolsTisLockThread.connect(self.SolsTisLockThread, self.SolsTisLockThread.signal,
                                           self.SolsTiSReLock)
            self.SolsTisLockThread.start()

    def SolsTiSReLock(self):
        progress = QtWidgets.QProgressDialog("Re-locking etalon", "Abort", 0, 5, self)
        progress.show()
        i = 0
        self.SolsTiS.system_status()

        while self.SolsTiS.laser_status['etalon_lock'] != 'on' and i < 5:
            progress.setValue(i)
            self.SolsTiS.etalon_lock('on')
            time.sleep(0.5)
            self.SolsTiS.system_status()
            time.sleep(0.1)
            i += 1
        progress.close()
        if i < 5:
            self.SolsTiSLockMonitor()
        else:
            popup = QtWidgets.QMessageBox()
            popup.setText("Re-locking the etalon failed")
            popup.exec_()

    def SolsTiSLockEtalon(self):
        if self.checkBoxSolsTiSEtalonLock.isChecked():
            self.SolsTiS.etalon_lock("on")
        else:
            self.SolsTiS.etalon_lock("off")

    def SolsTiSLockCavity(self):
        if self.checkBoxSolsTiSCavityLock.isChecked():
            self.SolsTiS.cavity_lock("on")
        else:
            self.SolsTiS.cavity_lock("off")

    def SolsTiSWL(self):
        wl = float(self.lineEditSolsTiSWL.text())
        self.SolsTiS.change_wavelength(wl)

    def updateGUI(self):
        self.lineEditSolsTiSWL.setText(str(self.SolsTiS.laser_status['wavelength']))
        self.checkBoxSolsTiSCavityLock.setChecked(
            self.SolsTiS.laser_status['cavity_lock'] in ['on'])
        self.checkBoxSolsTiSEtalonLock.setChecked(
            self.SolsTiS.laser_status['etalon_lock'] in ['on'])

    def SolsTiSMonitor(self):
        """Start (or restart) a background thread that polls the laser status periodically."""
        if self.SolsTiSMonitorThread is None:
            self.SolsTiSMonitorThread = SolsTiSStatusThread(self.SolsTiS)
            self.SolsTiSMonitorThread.connect(self.SolsTiSMonitorThread,
                                              self.SolsTiSMonitorThread.signal,
                                              self.SolsTiSupdatestatus)
            self.SolsTiSMonitorThread.start()
        elif not self.SolsTiSMonitorThread.isRunning():
            self.SolsTiSMonitorThread.start()

    def SolsTiSMonitorStop(self):
        """Terminate the status-monitor thread if it is running."""
        if self.SolsTiSMonitorThread is not None and self.SolsTiSMonitorThread.isRunning():
            self.SolsTiSMonitorThread.terminate()

    def SolsTiSupdatestatus(self):
        """Refresh the status table from ``laser_status``.

        ``relevant_properties`` maps display labels to the laser-status field names; the
        corresponding values are looked up and rendered as a two-column table.
        """
        relevant_properties = {
            'C. lock': 'cavity_lock',
            'E. lock': 'etalon_lock',
            'T': 'temperature',
            'R. volt.': 'resonator_voltage',
            'E. volt.': 'etalon_voltage',
            'wvl': 'wavelength',
            'Out': 'output_monitor'}
        display_dicc = {
            new_key: self.SolsTiS.laser_status[relevant_properties[new_key]]
            for new_key in list(relevant_properties.keys())}
        self.tableWidget.setRowCount(len(relevant_properties))
        row = 0
        for key in list(display_dicc.keys()):
            item_key = QtWidgets.QTableWidgetItem(key)
            item_value = QtWidgets.QTableWidgetItem(str(display_dicc[key]))
            self.tableWidget.setItem(row, 0, item_key)
            self.tableWidget.setItem(row, 1, item_value)
            row = row + 1
        self.tableWidget.resizeColumnsToContents()


class SolsTiSLockThread(QtCore.QThread):
    """Background thread that watches the etalon lock and signals when it drops out."""

    def __init__(self, solstis):
        QtCore.QThread.__init__(self)
        self.SolsTiS = solstis
        self.signal = QtCore.SIGNAL("laser_unlocked")

        self.setTerminationEnabled()

        self.SolsTiS.system_status()
        if self.SolsTiS.laser_status['etalon_lock'] != 'on':
            self.SolsTiS.etalon_lock('on')

    def run(self):
        while self.SolsTiS.laser_status['etalon_lock'] == 'on':
            time.sleep(2)
            self.SolsTiS.system_status()
            time.sleep(0.1)

        self.emit(self.signal)


class SolsTiSStatusThread(QtCore.QThread):
    """Background thread that polls ``system_status`` once per second and emits the result."""

    def __init__(self, solstis):
        QtCore.QThread.__init__(self)
        self.SolsTiS = solstis
        self.signal = QtCore.SIGNAL("SolsTiS_status_update")

        self.setTerminationEnabled()

        self.SolsTiS.system_status()

    def run(self):
        while 1:
            self.SolsTiS.system_status()

            self.emit(self.signal, self.SolsTiS.laser_status)

            time.sleep(1)


def download_logs():
    """Download the laser's automatic-logging files for a hard-coded date range.

    Note:
        Not general: the laser IP, date ranges, and output pickle path are hard-coded to a
        specific historical setup. Kept as a one-off helper rather than a reusable API.

    Returns:
        A list of the raw log file contents that were successfully downloaded.
    """

    def perdelta(start, end, delta):
        return_list = []
        curr = start
        while curr < end:
            # yield curr
            return_list.append(curr)
            curr += delta
        return [(int(x.strftime('%d')), int(x.strftime('%m')), int(x.strftime('%y')))
                for x in return_list]

    # import numpy as np
    from datetime import date
    from datetime import timedelta
    import urllib.error
    import urllib.parse
    import urllib.request

    url_name = 'http://172.24.37.153/FS/FLASH0/M_Squared/Logs/log_%d_%d_%d_%d.txt'

    # nums1 = [153, 222]
    # days = np.linspace(1, 32) #[1,2,3,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29]
    # months = np.linspace(1, 13)
    # years = [15, 16]

    # nums = [(153,18,8,16), (222,24,6,16), (222,23,6,16)]

    all_logs = []
    list_dates = perdelta(date(2016, 7, 12), date(2016, 11, 4), timedelta(days=1))
    for datum in list_dates:
        try:
            data = urllib.request.urlopen(url_name % ((153,) + datum))
            all_logs.append(data.read())
            print('Downloaded ', url_name % ((153,) + datum))
        except Exception as e:
            print('Failed ', url_name % ((153,) + datum), ' because ', e)
    list_dates = perdelta(date(2015, 7, 8), date(2016, 7, 11), timedelta(days=1))
    for datum in list_dates:
        try:
            data = urllib.request.urlopen(url_name % ((222,) + datum))
            all_logs.append(data.read())
            print('Downloaded ', url_name % ((222,) + datum))
        except Exception as e:
            print('Failed ', url_name % ((222,) + datum), ' because ', e)

    # for num in nums:
    #     try:
    #         data = urllib2.urlopen(url_name % num)
    #         all_logs.append(data.read())
    #         print 'Downloaded ', url_name % num
    #     except:
    #         print 'Failed ', url_name % num
    #     time.sleep(1)
    # for num1 in nums1:
    #     for day in days:
    #         for month in months:
    #             for year in years:
    #                 try:
    #                     data = urllib2.urlopen(url_name % (num1, day, month, year))
    #                     all_logs.append(data.read())
    #                     print 'Downloaded ', url_name % (num1, day, month, year)
    #                 except:
    #                     print 'Failed ', url_name % (num1, day, month, year)
    #                 time.sleep(1)
    import pickle
    pickle.dump(all_logs, open(r'C:\Users\Hera\Desktop/SolsTiSLogs.p', 'w'))
    return all_logs


ERROR_CODE = {
    1: 'JSON parsing, invalid start, wrong IP',
    2: '"message" string missing',
    3: '"transmission_id" string missing',
    4: 'No transmission id value',
    5: '"op" string missing',
    6: 'No op name',
    7: 'Operation not recognised',
    8: '"parameters" string missing',
    9: 'Invalid parameter tag of value'}
id_dictionary = {
    'move_wave_t': {
        'status': {
            0: 'Successful',
            1: 'Failed',
            2: 'Out of range'}},
    'poll_move_wave_t': {
        'status': {
            0: 'Tuning completed',
            1: 'Tuning in progress',
            2: 'Tuning failed'}},
    'stop_move_wave_t': {
        'status': {
            0: 'Completed'}},
    'tune_etalon': {
        'status': {
            0: 'Completed',
            1: 'Out of range',
            2: 'Failed'}},
    'tune_cavity': {
        'status': {
            0: 'Completed',
            1: 'Out of range',
            2: 'Failed'}},
    'fine_tune_cavity': {
        'status': {
            0: 'Completed',
            1: 'Out of range',
            2: 'Failed'}},
    'tune_resonator': {
        'status': {
            0: 'Completed',
            1: 'Out of range',
            2: 'Failed'}},
    'fine_tune_resonator': {
        'status': {
            0: 'Completed',
            1: 'Out of range',
            2: 'Failed'}},
    'etalon_lock': {
        'status': {
            0: 'Completed',
            1: 'Failed'}},
    'etalon_lock_status': {
        'status': {
            0: 'Completed',
            1: 'Failed'}},
    'cavity_lock': {
        'status': {
            0: 'Completed',
            1: 'Failed'}},
    'cavity_lock_status': {
        'status': {
            0: 'Completed',
            1: 'Failed'}},
    'get_status': {
        'status': {
            0: 'Completed',
            1: 'Failed'}},
    'set_wave_m': {
        'status': {
            0: "success",
            1: "no link",
            2: "out of range",
            3: "unknown error"}},
    'poll_wave_m': {
        'status': {
            0: 'Tuning completed',
            1: 'Tuning in progress',
            2: 'Tuning failed'}}}

if __name__ == '__main__':
    laser = SolsTiS('172.24.37.153')
    laser.show_gui()
    # all_logs = download_logs()
