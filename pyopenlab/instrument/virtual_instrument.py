# -*- coding: utf-8 -*-
"""Run a 32-bit instrument from a 64-bit Python console (and vice versa).

The bridge is a pair of "virtual" instruments that communicate through shared
memory maps: a *speaker* in the original 64-bit console and a *listener* in a
spawned 32-bit console. The speaker forwards method calls to the listener, which
executes them against the real instrument and returns the results.
"""
import inspect
import mmap
import re
import time

import numpy as np

from pyopenlab.instrument.message_bus_instrument import MessageBusInstrument


class VirtualInstrument_listener(object):
    """The listening half of the virtual-instrument bridge.

    When subclassed alongside a real instrument, it creates shared memory maps
    and waits for commands. On receiving one it runs the named method and writes
    the result back through a second map. Runs in the 32-bit console.
    """

    def __init__(self, memory_size=65536, memory_identifier='VirtualInstMemory'):
        """Create the inbound and outbound shared memory maps.

        Args:
            memory_size: Size in bytes of the inbound command map; the outbound
                map is 100 times larger.
            memory_identifier: Base name for the memory maps, usually
                ``"VirtualInstMemory_<classname>"``.
        """
        self.memory_map_in = mmap.mmap(0, memory_size, memory_identifier + 'In')
        self.memory_map_out = mmap.mmap(0, memory_size * 100, memory_identifier + 'Out')
        self.end_line = 'THE END\n'
        self.out_size = memory_size * 100
        self.memory_identifier = memory_identifier
        np.set_printoptions(
            threshold=np.inf
        )  # Set the prints options so that the arrays are printed as strings with no shortening

    def begin_listening(self):
        """Run the never-ending listen loop.

        Polls the inbound memory map for commands, runs each through
        :meth:`run_command_str`, and writes any resulting data back through the
        outbound memory map.
        """
        running = True
        while running:
            time.sleep(0.01)
            self.memory_map_in.seek(0)
            command_str = self.memory_map_in.readline()
            self.memory_map_in.seek(0)
            self.memory_map_in.write(self.end_line)
            command_str = re.sub('\n', '', command_str)
            if command_str != self.end_line[:-1]:
                data = self.run_command_str(command_str)
                if data is not None:
                    self.memory_map_out.seek(0)
                    if not hasattr(data, '__iter__'):
                        data = (data,)
                    self.memory_map_out.write('data = [];')
                    for data_i in data:
                        try:
                            data_i_str = np.array_str(data_i)  # attempt to convert array's to a str
                            try:
                                self.memory_map_out.write('data.append(np.array(' + data_i_str +
                                                          '));')
                            except ValueError:
                                print('Memory map size error, Increase the output map size')

                        except AttributeError:
                            # If the data is not a numpy array it will be passed at its str representation...This should work for most dtypes?
                            self.memory_map_out.write('data.append(' + str(data_i) + ');')
                    self.memory_map_out.write('\n' + self.end_line)

    def run_command_str(self, input_str):
        """Parse and run a command encoded as a string.

        Args:
            input_str: Command of the form ``"method(name=value, ...)"``.
                Arguments, if any, must be named.

        Returns:
            Whatever the named method returns, or ``None`` if the method does
            not exist on this object.
        """
        command = re.sub(r'\((.*?)\)', '', input_str)
        if hasattr(self, command):
            #         print 'command' , command
            function = getattr(self, command)
            input_list = re.findall(r'\((.*?)\)', input_str)[0].split(',')
            if len(input_list) > 1:
                input_dict = {}
                for input_param in input_list:
                    input_param_split = input_param.split('=')
                    if len(input_param_split) == 2:
                        input_dict[input_param.split('=')[0]] = input_param.split('=')[1]
                    else:
                        print('Arguments must be named for use through VirtualInstrument')
                #           print 'input_dict', input_dict
                return function(**input_dict)
            else:
                #           print'got to run'
                return function()
            #            return_vals = exec('self.'+input_str)

        else:
            print(command, 'does not exist')


class VirtualInstrument_speaker(MessageBusInstrument):
    """The speaking half of the virtual-instrument bridge.

    When subclassed, it exposes read/write methods that pass commands to, and
    parse data from, the listener instrument over the shared memory maps. Runs
    in the original 64-bit console.
    """

    def __init__(self, memory_size=65536, memory_identifier='VirtualInstMemory'):
        """Create the inbound and outbound shared memory maps.

        Args:
            memory_size: Size in bytes of the inbound command map; the outbound
                map is 100 times larger.
            memory_identifier: Base name for the memory maps, usually
                ``"VirtualInstMemory_<classname>"``.
        """
        self.end_line = 'THE END\n'
        self.memory_map_in = mmap.mmap(0, memory_size, memory_identifier + 'In')
        self.memory_map_in.write(self.end_line)
        self.memory_map_out = mmap.mmap(0, memory_size * 100, memory_identifier + 'Out')
        self.memory_map_out.write(self.end_line)

        self.out_size = memory_size * 100
        self.memory_identifier = memory_identifier

    def read(self):
        """Read the outbound memory map and parse any returned data.

        Returns:
            The parsed data string on success, or ``None`` if nothing was read
            or the data could not be evaluated.
        """
        self.memory_map_out.seek(0)
        reading = True
        lines = ''
        while reading:
            new_line = self.memory_map_out.readline()
            #            print new_line
            if new_line == self.end_line:
                reading = False
            else:
                lines += new_line
            if new_line == '':
                return None
        data = re.sub('\n', '', lines)
        data = re.sub(r'\]  *\[', '],[', data)
        data = re.sub(r'([0-9])  *([0-9])', r'\1,\2', data)
        data = re.sub(r'([0-9])  *([0-9])', r'\1,\2', data)
        data = re.sub(' *', '', data)
        self.memory_map_out.seek(0)
        self.memory_map_out.write(self.end_line + '\n')
        try:
            exec(data)
            return data
        #        return data
        except:
            return None

    #     return lines
    def _write(self, command):
        """Write a command string to the inbound memory map.

        Args:
            command: The command (method name and arguments) to send.
        """
        self.memory_map_in.seek(0)
        self.memory_map_in.write(command + '\n')
        self.memory_map_in.write(self.end_line)


def function_builder(command_name):
    """Build a speaker-side wrapper that forwards a method call to the listener.

    Args:
        command_name: Name of the method to forward.

    Returns:
        A function that serialises its arguments, writes the call to the inbound
        memory map, and returns the listener's parsed reply.
    """

    def wrapped_function(*args, **kwargs):
        input_str = ''
        obj = args[0]
        if len(args) > 1:
            for input_value in args[1:]:
                input_str += str(input_value) + ','

        for input_name, input_value in list(kwargs.items()):
            input_str = input_str + input_name + '=' + input_value + ','
        input_str = input_str[:-1]
        obj.memory_map_in.seek(0)
        obj.memory_map_in.write(command_name + '(' + input_str + ')\n')
        print(command_name + '(' + input_str + ')\n')
        time.sleep(1)
        return obj.read()

    return wrapped_function


def create_speaker_class(original_class):
    """Create a speaker instance for an instrument class.

    Subclasses ``original_class`` and replaces each method with a write command
    that forwards the call to the listener.

    Args:
        original_class: The instrument class to wrap.

    Returns:
        An instance of the generated speaker class.
    """

    class original_class_Stripped(original_class):  # copies the class

        def __init__(self):
            original_class.__init__(self)

    for command_name in list(original_class.__dict__.keys()):  # replaces any method
        command = getattr(original_class_Stripped, command_name)
        if inspect.ismethod(command):
            setattr(original_class_Stripped, command_name, function_builder(command_name))

    class virtual_speaker_class(
            original_class_Stripped, VirtualInstrument_speaker
    ):  # creates the new class by sublcassing the stripped class and the speaker class

        def __init__(self,
                     memory_size=65536,
                     memory_identifier='VirtualInstMemory_' + original_class.__name__):
            VirtualInstrument_speaker.__init__(self, memory_size, memory_identifier)

    return virtual_speaker_class()


def create_listener_class(original_class):
    """Create a listener class for an instrument class.

    Args:
        original_class: The instrument class the listener will subclass.

    Returns:
        A new class subclassing both ``original_class`` and
        :class:`VirtualInstrument_listener`.
    """

    class virtual_listener(original_class, VirtualInstrument_listener):

        def __init__(self,
                     memory_size=65536,
                     memory_identifier='VirtualInstMemory_' + original_class.__name__):
            original_class.__init__(self)
            VirtualInstrument_listener.__init__(self, memory_size, memory_identifier)

    return virtual_listener


def create_listener_by_name(module_name, class_name):
    """Create a listener class from the names of its module and class.

    Args:
        module_name: Importable module path containing the instrument class.
        class_name: Name of the instrument class within that module.

    Returns:
        The generated listener class.
    """
    exec('from ' + (module_name + " import " + class_name) + ' as ' + class_name)
    exec('virtual_listener=create_listener_class(' + class_name + ')')
    return virtual_listener


def setup_communication(original_class):
    """Create the paired speaker and listener for an instrument.

    The speaker is created in the current console; the listener is launched in a
    32-bit Python console via ``subprocess``.

    Args:
        original_class: The instrument to create in the 32-bit console.

    Returns:
        tuple: ``(speaker_class, listener_console)`` where ``speaker_class`` is
        the speaker instance used to control the instrument and
        ``listener_console`` is the :class:`subprocess.Popen` running the
        listener.
    """
    speaker_class = create_speaker_class(original_class)
    import subprocess
    command_str = "exec(\'import qtpy;from pyopenlab.instrument.virtual_instrument import inialise_listenser;inialise_listenser(" + r"\"" + original_class.__module__ + r"\",\"" + original_class.__name__ + r"\"" + ")')"
    listner_console = subprocess.Popen(["python32", "-c", command_str])
    return speaker_class, listner_console


# TODO: create an escape loop option for listening
def inialise_listenser(module_name, class_name):
    """Create the listener and start its loop. Called inside the 32-bit console.

    Args:
        module_name: Importable module path containing the instrument class.
        class_name: Name of the instrument class within that module.
    """
    #   print 'start'
    listener_class = create_listener_by_name(module_name, class_name)
    listener = listener_class()
    listener.begin_listening()


#   print 'hello'
#  return 1

if __name__ == '__main__':
    from pyopenlab.instrument.camera import DummyCamera

    speaker_cam, listener_console_cam = setup_communication(DummyCamera)
