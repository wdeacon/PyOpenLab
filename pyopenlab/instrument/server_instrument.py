# -*- coding: utf-8 -*-
"""
Functions for TCP server and client class creation for pyopenlab instruments.

For example, you might have an instrument that needs to be connected to a particular computer (e.g. because of an
acquisition card, or because it only has 32bit DLLs), but you want to run your experiment from another computer (e.g. a
64bit computer). The create_server_class and create_client_class functions allows you to create a server instance that
will run on the computer connected to the instrument, and a client instance that will run on your desired computer.

The create_client_class creates a class that overrides the class' __dict__ values so that when you call a class method
(e.g. camera.capture()), it creates a string message that is sent over TCP (e.g. "{'command': 'capture'}").
The create_server_class creates a class that reads these messages and passes them on appropriately to the instrument
instance.

For TCP messaging we use repr and ast.literal_eval instead of json.dumps and json.loads because they allow us to easily
send Python lists/tuples

NOTE: class.__dict__ does not contain superclass attributes or methods, so by default we only override the class methods
    but not any of the base classes. If you want to also send the superclass methods to the server, you need to
    explicitly list which methods you want to send
    (https://stackoverflow.com/questions/7241528/python-get-only-class-attribute-no-superclasses)

WARN: this has not been extensively tested, and can definitely have some issues if the user is not careful about
    thinking what functions and replies he wants to send over the TCP communication and which ones he doesn't (e.g. you
    would not want to send the instrument.show_gui() command through TCP), and also that PyQT signals are not --and
    cannot be-- sent through the TCP, which might cause some confusion.

EXAMPLE:
    Creating a server and client instruments for a Princeton Instruments PVCAM which only has 32bit DLLs that do not
    work in Windows 10. First create a client class that also sends PvcamSdk functions to the server. You might want to
    also add a list of the pyopenlab.instrument.camera methods:
    >>>> camera_client = create_client_class(Pvcam,
    >>>>                                     PvcamSdk.__dict__.keys() + ["get_camera_parameter", "set_camera_parameter"],
    >>>>                                     ('get_qt_ui', "raw_snapshot", "get_control_widget", "get_preview_widget"))
    >>>> camera_server = create_server_class(Pvcam)
    Then, on the computer connected to the camera, run:
    >>>> camera = camera_server((IP, port), 0)
    >>>> camera.run()
    And on the client computer run:
    >>>> camera = camera_client((IP, port))
    >>>> camera.show_gui()
"""
from future import standard_library

standard_library.install_aliases()
import ast
from builtins import str
import inspect
import re
import socket
import socketserver
import sys
import threading

import numpy as np

from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
from pyopenlab.utils.log import create_logger

BUFFER_SIZE = 3131894
message_end = 'tcp_termination'.encode()


def parse_arrays(value):
    """Convert a value (including arrays) to a string for sending over TCP.

    Args:
        value: The value to serialise. ``ArrayWithAttrs`` and ``ndarray`` are
            encoded as dicts; anything else is passed through ``repr``.

    Returns:
        str: The ``repr`` of the serialisable form of ``value``.
    """
    if type(value) == ArrayWithAttrs:
        reply = repr(dict(array=value.tolist(), attrs=value.attrs))
    elif type(value) == np.ndarray:
        reply = repr(dict(array=value.tolist()))
    else:
        reply = repr(value)
    return reply


def parse_strings(value):
    """Convert a TCP string back into a value, reconstructing arrays.

    Args:
        value: A string (or already-decoded dict) produced by
            :func:`parse_arrays`.

    Returns:
        The reconstructed value: an ``ArrayWithAttrs``, ``ndarray``, or the
        original value.
    """
    if not isinstance(value, dict):
        value = ast.literal_eval(value)
    if isinstance(value, dict):
        if 'array' in value and 'attrs' in value:
            return ArrayWithAttrs(value['array'], value['attrs'])
        elif 'array' in value:
            return np.array(value['array'])
    else:
        return value


def subselect(string, size=100):
    """Shorten a string for logging, keeping its head and tail.

    Args:
        string: The string to shorten.
        size: Maximum length before the middle is elided.

    Returns:
        The original string if short enough, otherwise its first and last
        ``size/2`` characters joined by ``" ... "``.
    """
    if len(string) > size:
        return '%s ... %s' % (string[:int(size / 2)], string[-int(size / 2):])
    else:
        return string


class ServerHandler(socketserver.BaseRequestHandler):
    """Request handler that maps one TCP message to one instrument action."""

    def handle(self):
        """Read a command, run it against the instrument, and send the reply.

        Reads a complete (``message_end``-terminated) request, dispatches it as
        an attribute listing, method call, or variable get/set, then serialises
        the result back to the client. Errors are caught and returned as an
        ``{'error': ...}`` reply.
        """
        try:
            raw_data = self.request.recv(BUFFER_SIZE).strip()
            while message_end not in raw_data:
                raw_data += self.request.recv(BUFFER_SIZE).strip()
            raw_data = re.sub(re.escape(message_end) + b'$', b'', raw_data)
            self.server._logger.debug("Server received: %s" % subselect(raw_data))

            if raw_data == b"list_attributes":
                instr_reply = list(self.server.instrument.__dict__.keys())
            else:
                command_dict = ast.literal_eval(raw_data.decode())
                if "command" in command_dict:
                    if "args" in command_dict and "kwargs" in command_dict:
                        instr_reply = getattr(self.server.instrument,
                                              command_dict["command"])(*command_dict["args"],
                                                                       **command_dict["kwargs"])
                    elif "args" in command_dict:
                        instr_reply = getattr(self.server.instrument,
                                              command_dict["command"])(*command_dict["args"])
                    elif "kwargs" in command_dict:
                        instr_reply = getattr(self.server.instrument,
                                              command_dict["command"])(**command_dict["kwargs"])
                    else:
                        instr_reply = getattr(self.server.instrument, command_dict["command"])()
                elif "variable_get" in command_dict:
                    instr_reply = getattr(self.server.instrument, command_dict["variable_get"])
                elif "variable_set" in command_dict:
                    setattr(self.server.instrument, command_dict["variable_set"],
                            parse_strings(command_dict["variable_value"]))
                    instr_reply = ''
                else:
                    instr_reply = "Dictionary did not contain a 'command' or 'variable' key"
        except Exception as e:
            self.server._logger.warn(e)
            instr_reply = dict(error=e)
        self.server._logger.debug("Instrument reply: %s" % subselect(str(instr_reply)))

        try:
            if type(instr_reply) == ArrayWithAttrs:
                reply = repr(dict(array=instr_reply.tolist(), attrs=instr_reply.attrs))
            elif type(instr_reply) == np.ndarray:
                reply = repr(dict(array=instr_reply.tolist()))
            else:
                reply = repr(instr_reply)
        except Exception as e:
            self.server._logger.warn(e)
            reply = repr(dict(error=str(e)))
        self.request.sendall(reply.encode() + message_end)
        self.server._logger.debug("Server replied %s %s: %s" %
                                  (len(reply), sys.getsizeof(reply), subselect(reply)))


def create_server_class(original_class):
    """Build a TCP server class wrapping a PyOpenLab instrument class.

    Args:
        original_class: A PyOpenLab instrument class.

    Returns:
        A ``socketserver.TCPServer`` subclass that owns an instrument instance
        and serves it over TCP.
    """

    class Server(socketserver.TCPServer):

        def __init__(self, server_address, *args, **kwargs):
            """Create the server and the instrument it serves.

            Args:
                server_address: ``(ip, port)`` for the server to listen on.
                *args: Positional arguments forwarded to the instrument.
                **kwargs: Keyword arguments forwarded to the instrument.
            """
            socketserver.TCPServer.__init__(self, server_address, ServerHandler, True)
            self.instrument = original_class(*args, **kwargs)
            self._logger = create_logger('TCP server')
            self.thread = None

        def run(self, with_gui=True, backgrounded=False):
            """Start serving requests.

            Args:
                with_gui: If True, serve in a background thread and open the
                    instrument GUI.
                backgrounded: If True, serve in a background thread without a
                    GUI. Ignored when ``with_gui`` is set.
            """
            if with_gui or backgrounded:
                if self.thread is not None:
                    del self.thread
                self.thread = threading.Thread(target=self.serve_forever)
                self.thread.setDaemon(True)  # don't hang on exit
                self.thread.start()
                if with_gui:
                    self.instrument.show_gui()
            else:
                self.serve_forever()

    return Server


def create_client_class(original_class,
                        tcp_methods=None,
                        excluded_methods=('get_qt_ui', "get_control_widget", "get_preview_widget"),
                        tcp_attributes=None,
                        excluded_attributes=('ui', '_ShowGUIMixin__gui_instance')):
    """Build a TCP client class for a PyOpenLab instrument class.

    The returned class overrides selected methods so that, instead of running
    locally, they send a string over TCP to an instrument server of the same
    type. It can also get and set attributes on the server's instrument
    instance.

    Args:
        original_class: A PyOpenLab instrument class.
        tcp_methods: Iterable of method names to send over TCP. Defaults to
            ``original_class.__dict__.keys()`` excluding magic methods.
        excluded_methods: Methods that must not be sent over TCP (e.g.
            ``get_qt_ui``, which returns a server-local object).
        tcp_attributes: Attributes that should be read over TCP.
        excluded_attributes: Attributes that must stay local (e.g. GUI
            attributes), never read over TCP.

    Returns:
        A subclass of ``original_class`` acting as the TCP client.
    """

    def method_builder(method_name):
        """Build a client method that forwards a call to the server.

        Args:
            method_name: Name of the method to forward.

        Returns:
            A function that packs its arguments into a command dict, sends it to
            the server, and returns the (array-aware) reply.
        """

        def method(*args, **kwargs):
            obj = args[0]
            command_dict = dict(command=method_name)
            if len(args) > 1:
                command_dict["args"] = args[1:]
            if len(list(kwargs.keys())) > 0:
                command_dict["kwargs"] = kwargs
            reply = obj.send_to_server(repr(command_dict))
            if type(reply) == dict:
                if "array" in reply:
                    if "attrs" in reply:
                        reply = ArrayWithAttrs(np.array(reply["array"]), reply["attrs"])
                    else:
                        reply = np.array(reply["array"])
            return reply

        return method

    class NewClass(original_class):

        def __init__(self, address):
            """Connect to the server and fetch its instrument's attribute list.

            Args:
                address: ``(ip, port)`` of the server to connect to.
            """
            self.address = address
            self._logger = create_logger(original_class.__name__ + '_client')
            self.instance_attributes = self.send_to_server("list_attributes", address)

        def __setattr__(self, item, value):
            """Set an attribute locally or forward it to the server.

            Methods and explicitly-local attributes are set locally; attributes
            belonging to the server's instrument are sent over TCP.

            Args:
                item: Attribute name.
                value: Value to assign.
            """
            # print "Setting: ", item
            # If the item is a method, pass it to the NewClass so that it can be sent to the server
            if item in self.method_list:
                super(NewClass, self).__setattr__(item, value)
            # If the item is a local attribute, set it locally
            elif item in ['instance_attributes', 'address', '_logger'] + excluded_attributes:
                original_class.__setattr__(self, item, value)
            # If the item is an attribute of the server instrument, send it over TCP. Note this if needs to happen after
            # the previous one, since it needs to use the self.instance_attributes
            elif item in self.instance_attributes or item in tcp_attributes:
                self.send_to_server(
                    repr(dict(variable_set=item, variable_value=parse_arrays(value))))
            else:
                original_class.__setattr__(self, item, value)

        def send_to_server(self, tcp_string, address=None):
            """Send a string to the server and return its evaluated reply.

            Opens a socket, sends ``tcp_string``, reads the full reply, and
            evaluates it with :func:`ast.literal_eval`.

            Args:
                tcp_string: String (or bytes) to send over TCP.
                address: ``(ip, port)`` to send to; defaults to ``self.address``.

            Returns:
                The reply parsed with :func:`ast.literal_eval`.

            Raises:
                RuntimeError: If the server reports an error in its reply.
            """
            if address is None:
                address = self.address
            if isinstance(tcp_string, str):
                tcp_string = tcp_string.encode()
            self._logger.debug("Client sending: %s" % subselect(tcp_string))
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect(address)
                sock.sendall(tcp_string + message_end)
                self._logger.debug("Client sent: %s" % subselect(tcp_string))
                received = sock.recv(BUFFER_SIZE)
                while message_end not in received:
                    received += sock.recv(BUFFER_SIZE)
                received = re.sub(re.escape(message_end) + b'$', b'', received)
                self._logger.debug("Client received: %s" % subselect(received))
                sock.close()
                if b'error' in received:
                    raise RuntimeError('Server error: %s' % subselect(received))
            except Exception as e:
                raise e
            return ast.literal_eval(received.decode())

    if tcp_methods is None:
        tcp_methods = list(original_class.__dict__.keys())
    excluded_methods = list(excluded_methods)
    if tcp_attributes is None:
        tcp_attributes = list()
    excluded_attributes = list(excluded_attributes)

    methods = []
    for command_name in tcp_methods:
        command = getattr(NewClass, command_name)
        # only replaces methods that are not magic (__xx__) and are not explicitly excluded
        if (inspect.ismethod(command) or inspect.isfunction(command)
            ) and not command_name.startswith('__') and command_name not in excluded_methods:
            setattr(NewClass, command_name, method_builder(command_name))
            methods += [command_name]
    setattr(NewClass, "method_list", methods)

    def my_getattr(self, item):
        # print("Getting: ", item, item in ["address", "instance_attributes"])
        if item in ["address", "instance_attributes", "method_list", "_logger", "__init__"
                    ] + excluded_attributes:
            # print('Excluded attribute: %s' % item)
            return object.__getattribute__(self, item)
            # return object.__getattr__(self, item)
        elif item in self.instance_attributes or item in tcp_attributes:
            # print('TCP: %s' % item)
            return self.send_to_server(repr(dict(variable_get=item)))
        elif item in excluded_methods:
            # print('Excluded method: %s' % item)
            # return original_class.__getattribute__(self, item)
            return original_class.__getattr__(self, item)
        else:
            return super(NewClass, self).__getattr__(item)

    setattr(NewClass, "__getattr__", my_getattr)

    return NewClass
