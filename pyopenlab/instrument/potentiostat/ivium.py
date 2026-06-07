# -*- coding: utf-8 -*-
"""Driver for Ivium potentiostats via the ``pyvium`` library.

Wraps :class:`pyvium.Pyvium` as a PyOpenLab :class:`Instrument`, adding
HDF5-backed saving and convenience methods for running cyclic voltammetry
(:meth:`Ivium.run_cv`) and chronoamperometry (:meth:`Ivium.run_ca`).
"""

import ctypes
import glob
import os.path
import time

import numpy as np
import pandas as pd
import pyvium
from pyvium import Pyvium
from pyvium.pyvium_verifiers import PyviumVerifiers

from pyopenlab import datafile as df
from pyopenlab.instrument import Instrument
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs


class Ivium(Instrument, Pyvium):
    """Instrument wrapper for an Ivium potentiostat.

    Built on the ``pyvium`` library (``pip install pyvium``). On construction it
    opens the Ivium driver, connects the device, verifies its status and
    attaches the current HDF5 datafile for saving results.

    Note:
        Method parameters must be passed as arguments to :meth:`run_cv` /
        :meth:`run_ca`; parameters edited in IviumSoft are neither saved to the
        ``.h5`` metadata nor read back. Parameter values are not validated
        against the instrument, so invalid inputs fall back to the defaults in
        the method file without warning.
    """

    def __init__(self):
        """Open the Ivium driver, connect the device and attach a datafile.

        Raises:
            AssertionError: If the connected device does not report a ready
                status.
        """
        Instrument.__init__(self)

        # Open Ivium dll & connect device

        self.open_driver()
        self.connect_device()

        # Check Ivium status

        self.status = self.get_device_status()
        assert self.status[0] == 1, 'Check Ivium status'
        print('Ivium connected!')

        # Create h5 datafile if none

        self.data_file = df.current()

    def save(self, name, data):
        """Save a dataset to the ``Potentiostat`` group of the HDF5 file.

        Uses the current datafile group if one is active, otherwise an existing
        or newly created ``Potentiostat`` group.

        Args:
            name: Name of the dataset to create.
            data: Array-like data to store (e.g. an ``ArrayWithAttrs``).
        """
        if self.data_file is None:
            self.data_file = df.current()

        ## Get current group or make 'Potentiostat' group
        if df._use_current_group == True and df._current_group is not None:
            group = df._current_group
        elif 'Potentiostat' in list(self.data_file.keys()):
            group = self.data_file['Potentiostat']
        else:
            group = self.data_file.create_group('Potentiostat')

        ## Save to group
        group.create_dataset(name=name, data=data)

    def run_cv(
            self,
            title: str = 'CV_%d',
            mode: str = 'Standard',
            e_start: float = 0,
            vertex_1: float = 1.0,
            vertex_2: float = -1.0,
            e_step: float = 0.1,
            n_scans: int = 1,
            scanrate: float = 1,
            current_range: str = '1nA',
            method_file_path:
        str = r"C:\Users\HERA\Documents\GitHub\pyopenlab\pyopenlab\instrument\potentiostat\CV_Standard.imf",
            save: bool = True):
        """Configure and run a cyclic voltammetry (CV) method, returning data.

        Args:
            title: Dataset/method title. Defaults to ``'CV_%d'``.
            mode: CV mode; must be ``'Standard'`` or ``'HiSpeed'``.
            e_start: Starting potential in V.
            vertex_1: Vertex 1 potential in V.
            vertex_2: Vertex 2 potential in V.
            e_step: Potential step size in V.
            n_scans: Number of CV scans.
            scanrate: CV scan rate in V/s.
            current_range: Current dynamic range; must be in the valid set
                (``'1A'`` through ``'100pA'``).
            method_file_path: Path to the CV ``.imf`` method file.
            save: If ``True``, save the result to the HDF5 file.

        Returns:
            ArrayWithAttrs: A ``[potential, current]`` array with measurement
            metadata attached.

        Raises:
            ValueError: If ``mode`` or ``current_range`` is invalid.
        """
        # Load CV method

        self.load_method(method_file_path)

        # Assert dropdown parameters are valid

        ## Mode
        if str(mode) != 'Standard' and str(mode) != 'HiSpeed':
            raise ValueError('\nInvalid CV mode. CV mode must be "Standard" or "HiSpeed"')
            return

        ## Current range
        valid_current_range = [
            '1A', '100mA', '10mA', '1mA', '100uA', '10uA', '1uA', '100nA', '10nA', '1nA', '100pA']
        if str(current_range) not in valid_current_range:
            raise ValueError('\nInvalid current range. Current range must be:\n' +
                             str(valid_current_range))
            return

        # Set all parameters

        self.set_method_parameter('Title', str(title))
        self.set_method_parameter('Mode', str(mode))
        self.set_method_parameter('E start', str(e_start))
        self.set_method_parameter('Vertex 1', str(vertex_1))
        self.set_method_parameter('Vertex 2', str(vertex_2))
        self.set_method_parameter('E step', str(e_step))
        self.set_method_parameter('N scans', str(n_scans))
        self.set_method_parameter('Scanrate', str(scanrate))
        self.set_method_parameter('Current range', str(current_range))

        # Run method

        ## Start method
        start_time = time.time()
        self.start_method()

        ## Wait for method to finish
        while self.get_device_status()[0] == 2:
            time.sleep(0.1)
        stop_time = time.time()
        print('Ivium method finished!')

        # Return data

        ## Get data
        total_points = self.get_available_data_points_number()
        data_t = []
        data_V = []
        data_I = []
        for point_index in range(1, total_points + 1):
            V_x, I, V = self.get_data_point(point_index)
            t = point_index * (e_step / scanrate)
            data_t.append(t)
            data_V.append(V)
            data_I.append(I)
        data_t = np.array(data_t)
        data_V = np.array(data_V)
        data_I = np.array(data_I)
        data_VI = np.array([data_V, data_I])

        ## Get attributes
        data_attrs = {
            'Potential (V)': data_V,
            'Time (s)': data_t,
            'Title': str(title),
            'Mode': str(mode),
            'E start (V)': e_start,
            'Vertex 1 (V)': vertex_1,
            'Vertex 2 (V)': vertex_2,
            'E step (V)': e_step,
            'N scans': n_scans,
            'Scanrate (V/s)': scanrate,
            'Current range': str(current_range),
            'start_time': start_time,
            'stop_time': stop_time}

        ## Return/save data
        if save == True:
            self.save(name=title, data=ArrayWithAttrs(data_VI, data_attrs))
        return ArrayWithAttrs(data_VI, data_attrs)

    def run_ca(
            self,
            title: str = 'CA_%d',
            mode: str = 'Standard',
            levels_v: list = [0, 0.5, 1.0],
            levels_t: list = [1, 1, 1],
            cycles: int = 5,
            interval_time: float = 0.1,
            current_range: str = '1nA',
            method_file_path:
        str = r"C:\Users\HERA\Documents\GitHub\pyopenlab\pyopenlab\instrument\potentiostat\CA_Standard.imf",
            save: bool = True):
        """Configure and run a chronoamperometry (CA) method, returning data.

        Args:
            title: Dataset/method title. Defaults to ``'CA_%d'``.
            mode: CA mode; must be ``'Standard'`` or ``'HiSpeed'``.
            levels_v: CA level potentials in V.
            levels_t: CA level times in s. Must match the length of ``levels_v``.
            cycles: Number of CA cycles.
            interval_time: CA data-point step size in s.
            current_range: Current dynamic range; must be in the valid set
                (``'1A'`` through ``'100pA'``).
            method_file_path: Path to the CA ``.imf`` method file.
            save: If ``True``, save the result to the HDF5 file.

        Returns:
            ArrayWithAttrs: A ``[time, current]`` array with measurement
            metadata attached.

        Raises:
            ValueError: If ``mode`` or ``current_range`` is invalid, if
                ``levels_v`` and ``levels_t`` differ in length, or if the number
                of levels is not between 1 and 25.
        """
        # Load CA method

        self.load_method(method_file_path)

        # Assert dropdown parameters are valid

        ## Mode
        if str(mode) != 'Standard' and str(mode) != 'HiSpeed':
            raise ValueError('\nInvalid CA mode. CA mode must be "Standard" or "HiSpeed"')
            return

        ## Current range
        valid_current_range = [
            '1A', '100mA', '10mA', '1mA', '100uA', '10uA', '1uA', '100nA', '10nA', '1nA', '100pA']
        if str(current_range) not in valid_current_range:
            raise ValueError('\nInvalid current range. Current range must be:\n' +
                             str(valid_current_range))
            return

        # Handle levels

        ## Assert number of level voltages and level times are the same
        if len(levels_v) != len(levels_t):
            raise ValueError(
                '\nInvalid CA levels. Number of voltages and times must be equal (len(levels_v) == len(levels_t)):\n'
            )
            print(len(levels_v) + ' voltage levels specified.\n')
            print(len(levels_t) + ' time levels specified.\n')
            return

        ## Assert 0 < number of levels <= 25
        if len(levels_v) < 1:
            raise ValueError('\nInvalid CA levels. Must specify at least 1 level:\n')
            return
        if len(levels_v) > 25:
            raise ValueError('\nInvalid CA levels. Cannot specify more than 25 levels:\n')
            return

        ## Set level parameters
        self.set_method_parameter('Levels', str(len(levels_v)))
        for i in range(0, len(levels_v)):
            level_i = i + 1
            self.set_method_parameter(f'Levels.E[{level_i}]', str(levels_v[i]))
            self.set_method_parameter(f'Levels.time[{level_i}]', str(levels_t[i]))

        # Set all parameters

        self.set_method_parameter('Title', str(title))
        self.set_method_parameter('Mode', str(mode))
        self.set_method_parameter('Cycles', str(cycles))
        self.set_method_parameter('Interval time', str(interval_time))
        self.set_method_parameter('Current range', str(current_range))

        # Run method

        ## Start method
        start_time = time.time()
        self.start_method()

        ## Wait for method to finish
        while self.get_device_status()[0] == 2:
            time.sleep(0.1)
        stop_time = time.time()
        print('Ivium method finished!')

        # Return data

        ## Get data
        total_points = self.get_available_data_points_number()
        data_t = []
        data_V = []
        data_I = []
        for point_index in range(1, total_points + 1):
            print(self.get_data_point(point_index))
            t, I, V = self.get_data_point(point_index)
            data_t.append(t)
            data_V.append(V)
            data_I.append(I)
        data_t = np.array(data_t)
        data_V = np.array(data_V)
        data_I = np.array(data_I)
        data_tI = np.array([data_t, data_I])

        ## Get attributes
        data_attrs = {
            'Potential (V)': data_V,
            'Time (s)': data_t,
            'Title': str(title),
            'Mode': str(mode),
            'N_levels': len(levels_v),
            'Levels_v (V)': levels_v,
            'Levels_t (s)': levels_t,
            'Cycles': cycles,
            'Interval time (s)': interval_time,
            'Current range': str(current_range),
            'start_time': start_time,
            'stop_time': stop_time}

        ## Return/save data
        if save == True:
            self.save(name=title, data=ArrayWithAttrs(data_tI, data_attrs))
        return ArrayWithAttrs(data_tI, data_attrs)


#%% Main

if __name__ == "__main__":

    ivium = Ivium()

#%% How to run from other scripts (e.g., as part of particle track)
'''
open Ivium Soft & connect Ivium

from pyopenlab.instruments.potentiostat.ivium import Ivium
ivium = Ivium()
# Put ivium object in lab equipment_dict

cv_data = ivium.run_cv() # Here specify the method/parameters you want to use from python (if you change parameters in Ivium soft, data will not be saved correctly)
lab.get_group().create_dataset(name = 'CV_%d', data = cv_data) # Use this line if you specify save = False in run_method() functions

#%%  Simultaneous (threaded) CV + SERS 

thread_cv = threading.Thread(target = ivium.run_cv, kwargs={'title': 'CV_test_%d'})
thread_SERS = threading.Thread(target = SERS_with_name, kwargs={'name': 'SERS_%d', 'laser_power': 0}) # Your SERS function here
thread_cv.start()
thread_SERS.start()
'''
