# -*- coding: utf-8 -*-
"""
Created on Mon Dec 05 17:41:32 2016

@author: Eoin

A Python file that allows you to run the databrowser from cmd line on a h5 file
"""


import pyopenlab.datafile as df
from pyopenlab.analysis import load_h5
data_file = df.DataFile(load_h5(), mode='r')
data_file.show_gui() #Show data browser
