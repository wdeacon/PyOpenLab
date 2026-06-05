# -*- coding: utf-8 -*-
"""Base class for instruments that communicate with line-based string messages.

Defines :class:`MessageBusInstrument`, the shared base for serial and VISA
instruments, along with the ``queried_property`` descriptors used to expose
instrument settings as ordinary Python attributes.
"""

from builtins import map
from builtins import object
from builtins import str
from builtins import zip
from functools import partial
import re
import threading
import types

import numpy as np
from past.builtins import basestring

import pyopenlab.instrument


class MessageBusInstrument(pyopenlab.instrument.Instrument):
    """An instrument that communicates by sending strings back and forth over a bus.

    This base class provides commonly-used mechanisms that support the use of
    serial or VISA instruments. The ``SerialInstrument`` and ``VISAInstrument``
    classes both inherit from it. Most interactions go through :meth:`query`,
    which writes a message and returns the reply.

    Subclassing:
        The minimum needed for a working subclass is to override :meth:`_write`
        and :meth:`readline`. A subclass usually also provides ``open()`` and
        ``close()`` methods for the underlying port, opens the port from
        ``__init__``, and overrides :meth:`flush_input_buffer` so a stale input
        buffer cannot corrupt a query.

    Threading:
        All access to the bus must be protected by :attr:`communications_lock`.
        The lock may also guard sequences of calls that must be atomic (e.g. a
        multi-part exchange), but should not be held longer than necessary, or
        other threads may block for a long time. The lock is reentrant, so
        acquiring it twice is safe.

    Attributes:
        termination_character (str): Character that terminates every message to
            or from the instrument.
        termination_read (str): Read terminator, when it differs from the write
            terminator. Currently honoured only by ``serial_instrument``.
        termination_line (str): Terminating string that marks the end of a
            multi-line response.
        ignore_echo (bool): If True, the instrument echoes commands back and the
            echo is consumed and checked after each write.
    """
    termination_character = "\n"
    termination_read = None
    termination_line = None
    ignore_echo = False

    _communications_lock = None

    @property
    def communications_lock(self):
        """threading.RLock: Reentrant lock protecting access to the bus.

        The lock is created lazily on first access, because subclasses are not
        guaranteed to call this class's ``__init__``.
        """
        if self._communications_lock is None:
            self._communications_lock = threading.RLock()
        return self._communications_lock

    def write(self, write_string, timeout=None, *args, **kwargs):
        """Write a string to the underlying communications port.

        Args:
            write_string: Message to send to the instrument.
            timeout: Timeout in seconds for consuming the echo when
                :attr:`ignore_echo` is set. ``None`` uses the port default.
            *args: Extra positional arguments forwarded to :meth:`_write`.
            **kwargs: Extra keyword arguments forwarded to :meth:`_write`.
        """
        with self.communications_lock:
            self._write(write_string, *args, **kwargs)
        self._check_echo(write_string, timeout)

    def _write(self, query_string, *args, **kwargs):
        """Send raw bytes to the port. Must be overridden by subclasses.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        raise NotImplementedError(
            "Subclasses of MessageBusInstrument must override the _write method!")

    def flush_input_buffer(self):
        """Discard anything waiting to be read on the bus.

        Override this so a stale input buffer cannot corrupt a subsequent query.
        The base implementation does nothing but acquire the lock.
        """
        with self.communications_lock:
            pass

    def readline(self, timeout=None):
        """Read one line from the underlying bus. Must be overridden.

        Args:
            timeout: Read timeout in seconds. ``None`` uses the port default.

        Raises:
            NotImplementedError: Always, unless overridden by a subclass.
        """
        with self.communications_lock:
            raise NotImplementedError(
                "Subclasses of MessageBusInstrument must override the readline method!")

    def read_multiline(self, termination_line=None, timeout=None):
        """Read lines from the bus until a termination line is seen.

        Repeatedly calls :meth:`readline` and concatenates the results. Override
        this only if there is a more efficient way to read multiple lines.

        Args:
            termination_line: Substring marking the final line. Falls back to
                :attr:`termination_line` when ``None``.
            timeout: Per-line read timeout in seconds, passed to
                :meth:`readline`.

        Returns:
            str: The concatenated multi-line response.

        Raises:
            AssertionError: If no termination line is available from either the
                argument or :attr:`termination_line`.
        """
        with self.communications_lock:
            if termination_line is None:
                termination_line = self.termination_line

            try:
                assert isinstance(
                    termination_line, basestring
                ), "If you perform a multiline query, you must specify a termination line either through the termination_line keyword argument or the termination_line property of the NPSerialInstrument."
            except NameError:
                assert isinstance(
                    termination_line, str
                ), "If you perform a multiline query, you must specify a termination line either through the termination_line keyword argument or the termination_line property of the NPSerialInstrument."

            response = ""
            last_line = "dummy"
            while termination_line not in last_line and len(
                    last_line) > 0:  # read until we get the termination line.
                last_line = self.readline(timeout)
                response += last_line
            return response

    def query(self, query_string, multiline=False, termination_line=None, timeout=None):
        """Write a string to the instrument and return its response.

        Blocks until a response is received. When ``multiline`` is set (or a
        ``termination_line`` is given) it keeps reading until the termination
        phrase is reached.

        Args:
            query_string: Message to send to the instrument.
            multiline: If True, read a multi-line response via
                :meth:`read_multiline`.
            termination_line: Substring marking the end of a multi-line
                response; supplying it implies ``multiline=True``.
            timeout: Read timeout in seconds. ``None`` uses the port default.

        Returns:
            str: The instrument's response, stripped of surrounding whitespace
            for single-line replies.
        """
        with self.communications_lock:
            self.flush_input_buffer()
            self.write(query_string, timeout)

            if termination_line is not None:
                multiline = True
            if multiline:
                return self.read_multiline(termination_line)
            else:
                return self.readline(
                    timeout).strip()  # question: should we strip the final newline?

    def _check_echo(self, echo_string, timeout=None):
        """Consume and verify the command echo when :attr:`ignore_echo` is set.

        Args:
            echo_string: The command that was written and is expected back.
            timeout: Read timeout in seconds for the echoed line.
        """
        if self.ignore_echo:
            echo_line = self.readline(timeout).strip()
            if echo_line != echo_string:
                self._logger.warn('Command did not echo: %s' % echo_string)

    def parsed_query_old(self,
                         query_string,
                         response_string=r"(\d+)",
                         re_flags=0,
                         parse_function=int,
                         **kwargs):
        """Perform a query and parse the result with a regular expression.

        By default it looks for an integer and returns one; otherwise it matches
        a custom regex and returns the subexpressions, each passed through
        ``parse_function``.

        Args:
            query_string: Message to send to the instrument.
            response_string: Regex matched against the response; each group is
                one returned item.
            re_flags: Flags passed to :func:`re.search`.
            parse_function: Callable applied to each matched group.
            **kwargs: Extra keyword arguments forwarded to :meth:`query`.

        Returns:
            The parsed group, or a list of parsed groups for multiple matches.

        Raises:
            ValueError: If the response does not match, or a group cannot be
                parsed by ``parse_function``.
        """
        # NB no need for the lock here - `query` is already an atomic operation.
        reply = self.query(query_string, **kwargs)
        res = re.search(response_string, reply, flags=re_flags)
        if res is None:
            raise ValueError("Stage response to '%s' ('%s') wasn't matched by /%s/" %
                             (query_string, reply, response_string))
        try:
            if len(res.groups()) == 1:
                return parse_function(res.groups()[0])
            else:
                return list(map(parse_function, res.groups()))
        except ValueError:
            raise ValueError(
                "Stage response to %s ('%s') couldn't be parsed by the supplied function" %
                (query_string, reply))

    def parsed_query(self,
                     query_string,
                     response_string=r"%d",
                     re_flags=0,
                     parse_function=None,
                     **kwargs):
        """Perform a query and return a parsed form of the response.

        Queries the instrument, then compares the response against a template.
        The template may contain literal text and ``sscanf``-style placeholders
        (e.g. ``%i`` for integers, ``%f`` for floats). Regular expressions are
        also allowed, with each group treated as one item to parse. Mixing
        ``%`` placeholders and regular expressions is not currently supported.

        When ``%i``/``%f``/etc. placeholders are used the returned values are
        converted automatically; otherwise ``parse_function`` must be supplied.

        Args:
            query_string: Message to send to the instrument.
            response_string: Template (placeholders and/or regex) matched
                against the response.
            re_flags: Flags passed to :func:`re.search`.
            parse_function: Callable applied to all groups, or a list of
                callables applied to each group in turn. Inferred from
                placeholders when ``None``.
            **kwargs: Extra keyword arguments forwarded to :meth:`query`.

        Returns:
            The parsed group, or a list of parsed groups for multiple matches.

        Raises:
            ValueError: If the response does not match the template, or a group
                cannot be parsed.
        """

        response_regex = response_string
        noop = lambda x: x  # placeholder null parse function
        placeholders = [  # tuples of (regex matching placeholder, regex to replace it with, parse function)
            (r"%c", r".", noop),
            (r"%(\\d+)c", r".{\1}", noop),  # TODO support %cn where n is a number of chars
            (r"%d", r"[-+]?\\d+", int),
            (r"%[eEfg]", r"[-+]?(?:\\d+(?:\.\\d*)?|\.\\d+)(?:[eE][-+]?\\d+)?", float),
            # (r"%(\\d+)c",r".{\\1}", noop), #TODO support %cn where n is a number of chars
            # (r"%d",r"[-+]?\\d+", int),
            # (r"%[eEfg]",r"[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][-+]?\\d+)?", float),
            (r"%i", r"[-+]?(?:0[xX][\\dA-Fa-f]+|0[0-7]*|\\d+)", lambda x: int(x, 0)
             ),  # 0=autodetect base
            (r"%o", r"[-+]?[0-7]+", lambda x: int(x, 8)),  # 8 means octal
            (r"%s", r"\\S+", noop),
            (r"%u", r"\\d+", int),
            (r"%[xX]", r"[-+]?(?:0[xX])?[\\dA-Fa-f]+",
             lambda x: int(x, 16)),  # 16 forces hexadecimal
        ]
        matched_placeholders = []
        for placeholder, regex, parse_fun in placeholders:
            response_regex = re.sub(placeholder, '(' + regex + ')',
                                    response_regex)  # substitute regex for placeholder
            matched_placeholders.extend([
                (parse_fun, m.start()) for m in re.finditer(placeholder, response_string)
            ])  # save the positions of the placeholders
        if parse_function is None:
            parse_function = [f for f, s in sorted(matched_placeholders, key=lambda m: m[1])
                              ]  # order parse functions by their occurrence in the original string
        if not hasattr(parse_function, '__iter__'):
            parse_function = [parse_function]  # make sure it's a list.

        reply = self.query(query_string, **kwargs)  # do the query
        res = re.search(response_regex, reply, flags=re_flags)
        if res is None:
            raise ValueError(
                "Stage response to '%s' ('%s') wasn't matched by /%s/ (generated regex /%s/" %
                (query_string, reply, response_string, response_regex))
        try:
            parsed_result = [f(g) for f, g in zip(parse_function, res.groups())
                             ]  # try to apply each parse function to its argument
            if len(parsed_result) == 1:
                return parsed_result[0]
            else:
                return parsed_result
        except ValueError:
            print("Parsing Error")
            print("Matched Groups:", res.groups())
            print("Parsing Functions:", parse_function)
            raise ValueError(
                "Stage response to %s ('%s') couldn't be parsed by the supplied function" %
                (query_string, reply))

    def int_query(self, query_string, **kwargs):
        """Perform a query and return the result(s) as integer(s).

        Args:
            query_string: Message to send to the instrument.
            **kwargs: Extra keyword arguments forwarded to :meth:`parsed_query`.

        Returns:
            The parsed integer, or a list of integers for multiple matches.
        """
        return self.parsed_query(query_string, "%d", **kwargs)

    def float_query(self, query_string, **kwargs):
        """Perform a query and return the result(s) as float(s).

        Args:
            query_string: Message to send to the instrument.
            **kwargs: Extra keyword arguments forwarded to :meth:`parsed_query`.

        Returns:
            The parsed float, or a list of floats for multiple matches.
        """
        return self.parsed_query(query_string, "%f", **kwargs)

    #@staticmethod  # this was an attempt at making a property factory - now using a descriptor
    #def queried_property(self, get_cmd, set_cmd, dtype='float', docstring=''):
    #    get_func = self.float_query if dtype=='float' else self.query
    #    return property(fget=partial(get_func, get_cmd), fset=self.write, docstring=docstring)


class queried_property(object):
    """A property-like descriptor that reads/writes a value over the bus.

    Use it in a class body just like :func:`property`. Getting the attribute
    issues ``get_cmd`` and parses the reply; setting it formats ``set_cmd`` with
    the value and writes it.

    Args:
        get_cmd: Command sent to read the value, or ``None`` for write-only.
        set_cmd: Command template sent to set the value (``{0}`` or ``%``
            formatting), or ``None`` for read-only.
        validate: Iterable of allowed values; a value outside it raises
            ``ValueError`` on set.
        valrange: ``(min, max)`` range; a value outside it raises ``ValueError``
            on set.
        fdel: Callable invoked when the attribute is deleted.
        doc: Docstring for the descriptor.
        dtype: Reply type: ``'float'``, ``'int'``, ``'bool'``, or anything else
            for a raw string.
    """

    def __init__(self,
                 get_cmd=None,
                 set_cmd=None,
                 validate=None,
                 valrange=None,
                 fdel=None,
                 doc=None,
                 dtype='float'):
        self.dtype = dtype
        self.get_cmd = get_cmd
        self.set_cmd = set_cmd
        self.validate = validate
        self.valrange = valrange
        self.fdel = fdel
        self.__doc__ = doc

    # TODO: standardise the return (single value only vs parsed result), consider bool
    def __get__(self, obj, objtype=None):
        """Read the value from the instrument, parsed according to ``dtype``.

        Returns:
            The descriptor itself when accessed on the class, otherwise the
            parsed value read from the instrument.

        Raises:
            AttributeError: If the descriptor is write-only (``get_cmd`` is
                ``None``).
        """
        if obj is None:
            return self
        if self.get_cmd is None:
            raise AttributeError("unreadable attribute")
        if self.dtype == 'float':
            getter = obj.float_query
        elif self.dtype == 'int':
            getter = obj.int_query
        else:
            getter = obj.query
        value = getter(self.get_cmd)
        if self.dtype == 'bool':
            value = bool(value)
        return value

    def __set__(self, obj, value):
        """Validate ``value`` and write it to the instrument via ``set_cmd``.

        Raises:
            AttributeError: If the descriptor is read-only (``set_cmd`` is
                ``None``).
            ValueError: If ``value`` fails the ``validate`` or ``valrange``
                check.
        """
        if self.set_cmd is None:
            raise AttributeError("can't set attribute")
        if self.validate is not None:
            if value not in self.validate:
                raise ValueError('invalid value supplied - value must be one of {}'.format(
                    self.validate))
        if self.valrange is not None:
            if value < min(self.valrange) or value > max(self.valrange):
                raise ValueError('invalid value supplied - value must be in the range {}-{}'.format(
                    *self.valrange))
        message = self.set_cmd
        if '{0' in message:
            message = message.format(value)
        elif '%' in message:
            message = message % value
        obj.write(message)

    def __delete__(self, obj):
        """Delete the attribute by invoking ``fdel``.

        Raises:
            AttributeError: If no ``fdel`` callable was supplied.
        """
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        self.fdel(obj)


class queried_channel_property(queried_property):
    """A :class:`queried_property` for one channel of a multi-channel instrument.

    The owning object must expose a ``ch`` attribute (the channel) and a
    ``parent`` attribute (the instrument on the bus). The channel is substituted
    into ``get_cmd``/``set_cmd`` before the parent issues the command.
    """

    # I'm not sure what this does or who uses it.  I assume it's Alan's? --rwb27
    def __init__(self,
                 get_cmd=None,
                 set_cmd=None,
                 validate=None,
                 valrange=None,
                 fdel=None,
                 doc=None,
                 dtype='float'):
        super(queried_channel_property, self).__init__(get_cmd, set_cmd, validate, valrange, fdel,
                                                       doc, dtype)

    def __get__(self, obj, objtype=None):
        """Read the value for this channel via the parent instrument.

        Returns:
            The parsed value for ``obj.ch``, read through ``obj.parent``.

        Raises:
            AssertionError: If ``obj`` lacks a ``ch`` or ``parent`` attribute.
            AttributeError: If the descriptor is write-only.
        """
        assert hasattr(obj, 'ch') and hasattr(obj, 'parent'),\
        'object must have a ch attribute and a parent attribute'
        if obj is None:
            return self
        if self.get_cmd is None:
            raise AttributeError("unreadable attribute")
        if self.dtype == 'float':
            getter = obj.parent.float_query
        elif self.dtype == 'int':
            getter = obj.parent.int_query
        else:
            getter = obj.parent.query
        message = self.get_cmd
        if '{0' in message:
            message = message.format(obj.ch)
        elif '%' in message:
            message = message % obj.ch
        value = getter(message)
        if self.dtype == 'bool':
            value = bool(value)
        return value

    def __set__(self, obj, value):
        """Validate ``value`` and write it for this channel via the parent.

        Raises:
            AssertionError: If ``obj`` lacks a ``ch`` or ``parent`` attribute.
            AttributeError: If the descriptor is read-only.
            ValueError: If ``value`` fails the ``validate`` or ``valrange``
                check.
        """
        assert hasattr(obj, 'ch') and hasattr(obj, 'parent'),\
        'object must have a ch attribute and a parent attribute'
        if self.set_cmd is None:
            raise AttributeError("can't set attribute")
        if self.validate is not None:
            if value not in self.validate:
                raise ValueError('invalid value supplied - value must be one of {}'.format(
                    self.validate))
        if self.valrange is not None:
            if value < min(self.valrange) or value > max(self.valrange):
                raise ValueError('invalid value supplied - value must be in the range {}-{}'.format(
                    *self.valrange))
        message = self.set_cmd
        if '{0' in message:
            message = message.format(obj.ch, value)
        elif '%' in message:
            message = message % (obj.ch, value)
        obj.parent.write(message)


class EchoInstrument(MessageBusInstrument):
    """Trivial test instrument, it simply echoes back what we write."""

    def __init__(self):
        super(EchoInstrument, self).__init__()
        self._last_write = ""

    def _write(self, msg, *args, **kwargs):
        self._last_write = msg

    def readline(self, timeout=None):
        return self._last_write


def wrap_with_echo_to_console(obj):
    """Patch an instrument so its bus traffic is echoed to the console.

    Replaces ``obj.write`` and ``obj.readline`` with wrappers that print the
    sent and received strings. Useful for debugging communications.

    Args:
        obj: A :class:`MessageBusInstrument` instance to patch in place.
    """
    import functools

    obj._debug_echo = True
    obj._original_write = obj.write
    obj._original_readline = obj.readline

    def write(self, q, *args, **kwargs):
        print("Sent: " + str(q))
        return self._original_write(q, *args, **kwargs)

    obj.write = functools.partial(write, obj)

    def readline(self, *args, **kwargs):
        ret = self._original_readline(*args, **kwargs)
        print("Recv: " + str(ret))
        return ret

    obj.readline = functools.partial(readline, obj)


if __name__ == '__main__':

    class DummyInstrument(EchoInstrument):
        x = queried_property('gx', 'sx {0}', dtype='str')

    instr = DummyInstrument()
    print(instr.x)
    instr.x = 'y'
    print(instr.x)
    instr.x = 'x'
    print(instr.x)
